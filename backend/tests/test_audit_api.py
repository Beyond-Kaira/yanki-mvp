"""The audit log as the Admin Panel queries it (P7.3 / P7.4).

Four properties this file exists to hold.

**It is org-scoped at the query, not filtered in the response.** ``org_id`` is
taken from the caller's context and is not a parameter, so no combination of
filters reaches another tenant's events. The cross-tenant tests here are the
ones that would catch a regression.

**Pagination is stable.** Events written inside one transaction share a
timestamp, and a sort with no tiebreaker then repeats rows across pages and
skips others. That is an ordinary annoyance in a list of products and a serious
one in a log somebody is reading to prove a negative.

**Redaction happened at write time.** These endpoints cannot leak a secret,
because there is no unredacted copy for them to read — proved by writing an
event with a password in it and looking for it in the response.

**Integrity is checkable.** A row edited behind the API's back reports itself
as altered rather than being silently served as fact.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import AuditEvent, Membership, Organization, User
from app.services import audit

SIGNUP = "/api/v1/auth/signup"
LOGIN = "/api/v1/auth/login"
EVENTS = "/api/v1/admin/audit-events"
MEMBERS = "/api/v1/admin/members"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def auth_settings(client: TestClient) -> Iterator[None]:
    settings = Settings(
        jwt_secret_key=SecretStr("a" * 64),
        jwt_issuer="test-yanki-api",
        jwt_audience="test-yanki-web",
        auth_refresh_cookie_secure=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


def _signup(client: TestClient, email: str, **extra) -> dict:
    response = client.post(SIGNUP, json={"email": email, "password": PASSWORD, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def _token(client: TestClient, email: str) -> str:
    response = client.post(LOGIN, json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str, org_id=None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id is not None:
        headers["X-Org-Id"] = str(org_id)
    return headers


def _owner_org(client: TestClient, db_session, name: str = "Acme") -> Organization:
    email = f"owner@{name.lower()}.test"
    _signup(client, email, account_type="organization", organization_name=name)
    org = db_session.scalar(sa.select(Organization).where(Organization.name == name))
    assert org is not None
    return org


def _seed(db_session, org, **kwargs) -> AuditEvent:
    """Write one event straight through the service, as a route would."""

    from app.services.tenancy import OrgContext

    event = audit.emit(
        db_session,
        context=OrgContext(org_id=org.id, user_id=None, role="owner"),
        **kwargs,
    )
    db_session.commit()
    return event


# --------------------------------------------------------------------------
# Access
# --------------------------------------------------------------------------


def test_reading_the_audit_log_requires_authentication(client):
    assert client.get(EVENTS).status_code == 401


def test_a_viewer_cannot_read_the_audit_log(client, db_session):
    org = _owner_org(client, db_session)
    _signup(client, "viewer@acme.test")
    user = db_session.scalar(sa.select(User).where(User.email == "viewer@acme.test"))
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="viewer", status="active"))
    db_session.commit()

    response = client.get(
        EVENTS, headers=_headers(_token(client, "viewer@acme.test"), org_id=org.id)
    )
    assert response.status_code == 403


def test_an_admin_can_read_the_audit_log(client, db_session):
    _owner_org(client, db_session)
    response = client.get(EVENTS, headers=_headers(_token(client, "owner@acme.test")))
    assert response.status_code == 200


# --------------------------------------------------------------------------
# What is recorded
# --------------------------------------------------------------------------


def test_a_member_change_lands_in_the_log_with_before_and_after(client, db_session):
    org = _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")
    _signup(client, "editor@acme.test")
    user = db_session.scalar(sa.select(User).where(User.email == "editor@acme.test"))
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="viewer", status="active"))
    db_session.commit()

    client.patch(f"{MEMBERS}/{user.id}", headers=_headers(owner), json={"role": "editor"})

    body = client.get(EVENTS, headers=_headers(owner), params={"action": "member:update"}).json()
    assert body["total"] == 1
    event = body["events"][0]
    assert event["entity_type"] == "user"
    assert event["entity_id"] == str(user.id)
    assert event["before"]["role"] == "viewer"
    assert event["after"]["role"] == "editor"
    assert event["changed"]["role"] == {"from": "viewer", "to": "editor"}
    assert event["outcome"] == "success"


def test_every_event_carries_the_request_id_and_a_hashed_ip(client, db_session):
    _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")

    response = client.get(EVENTS, headers=_headers(owner))
    body = response.json()
    assert body["total"] >= 1

    signup_event = next(e for e in body["events"] if e["action"] == "auth:signup")
    assert signup_event["request_id"]
    # Hashed, never the address itself — the same salted hash the rate limiter
    # uses, so one visitor looks like one visitor across both subsystems.
    assert signup_event["ip_hash"]
    assert len(signup_event["ip_hash"]) == 64
    assert "testclient" not in (signup_event["ip_hash"] or "")


def test_an_inbound_request_id_is_echoed_and_recorded(client, db_session):
    _signup(client, "owner@acme.test", account_type="organization", organization_name="Acme")
    response = client.post(
        LOGIN,
        json={"email": "owner@acme.test", "password": PASSWORD},
        headers={"X-Request-Id": "trace-abc-123"},
    )
    assert response.headers["x-request-id"] == "trace-abc-123"

    owner = response.json()["access_token"]
    body = client.get(EVENTS, headers=_headers(owner), params={"action": "auth:login"}).json()
    assert body["events"][0]["request_id"] == "trace-abc-123"


def test_a_hostile_request_id_is_replaced_rather_than_stored(client, db_session):
    _signup(client, "owner@acme.test", account_type="organization", organization_name="Acme")
    forged = "x" * 500 + "<script>"
    response = client.post(
        LOGIN,
        json={"email": "owner@acme.test", "password": PASSWORD},
        headers={"X-Request-Id": forged},
    )
    assert response.headers["x-request-id"] != forged

    owner = response.json()["access_token"]
    body = client.get(EVENTS, headers=_headers(owner), params={"action": "auth:login"}).json()
    assert body["events"][0]["request_id"] != forged
    assert len(body["events"][0]["request_id"]) == 32


def test_a_denied_action_is_recorded_as_denied(client, db_session):
    org = _owner_org(client, db_session)
    _signup(client, "viewer@acme.test")
    user = db_session.scalar(sa.select(User).where(User.email == "viewer@acme.test"))
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="viewer", status="active"))
    db_session.commit()

    client.get(MEMBERS, headers=_headers(_token(client, "viewer@acme.test"), org_id=org.id))

    body = client.get(
        EVENTS, headers=_headers(_token(client, "owner@acme.test")), params={"outcome": "denied"}
    ).json()
    assert body["total"] >= 1
    assert any(e["action"] == "member:read" for e in body["events"])


def test_secrets_never_reach_the_response(client, db_session):
    org = _owner_org(client, db_session)
    _seed(
        db_session,
        org,
        action="test:secret",
        actor_type="system",
        after={"password": "hunter2", "api_key": "sk-live-abc", "name": "fine"},
    )

    body = client.get(EVENTS, headers=_headers(_token(client, "owner@acme.test"))).json()
    assert "hunter2" not in str(body)
    assert "sk-live-abc" not in str(body)
    event = next(e for e in body["events"] if e["action"] == "test:secret")
    assert event["after"] == {
        "password": "[redacted]",
        "api_key": "[redacted]",
        "name": "fine",
    }


# --------------------------------------------------------------------------
# Filtering, searching, sorting, paging
# --------------------------------------------------------------------------


def test_filters_by_action_prefix(client, db_session):
    org = _owner_org(client, db_session)
    _seed(db_session, org, action="project:create", entity_type="project")
    _seed(db_session, org, action="project:delete", entity_type="project")
    _seed(db_session, org, action="billing:update", entity_type="subscription")

    owner = _headers(_token(client, "owner@acme.test"))
    assert client.get(EVENTS, headers=owner, params={"action": "project:"}).json()["total"] == 2
    assert (
        client.get(EVENTS, headers=owner, params={"action": "project:create"}).json()["total"] == 1
    )


def test_filters_by_entity_actor_outcome_and_date(client, db_session):
    org = _owner_org(client, db_session)
    actor = uuid.uuid4()
    entity = uuid.uuid4()
    _seed(
        db_session,
        org,
        action="thing:update",
        actor_type="user",
        actor_id=actor,
        entity_type="thing",
        entity_id=entity,
    )
    _seed(db_session, org, action="thing:update", entity_type="other", outcome="error")

    owner = _headers(_token(client, "owner@acme.test"))
    assert client.get(EVENTS, headers=owner, params={"entity_type": "thing"}).json()["total"] == 1
    assert client.get(EVENTS, headers=owner, params={"entity_id": str(entity)}).json()["total"] == 1
    assert client.get(EVENTS, headers=owner, params={"actor_id": str(actor)}).json()["total"] == 1
    assert client.get(EVENTS, headers=owner, params={"outcome": "error"}).json()["total"] == 1

    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    assert (
        client.get(EVENTS, headers=owner, params={"occurred_from": tomorrow}).json()["total"] == 0
    )
    assert client.get(EVENTS, headers=owner, params={"occurred_to": yesterday}).json()["total"] == 0
    assert (
        client.get(EVENTS, headers=owner, params={"occurred_from": yesterday}).json()["total"] > 0
    )


def test_a_malformed_date_is_a_422_rather_than_being_ignored(client, db_session):
    _owner_org(client, db_session)
    response = client.get(
        EVENTS,
        headers=_headers(_token(client, "owner@acme.test")),
        params={"occurred_from": "last tuesday"},
    )
    assert response.status_code == 422


def test_search_covers_the_human_readable_columns(client, db_session):
    org = _owner_org(client, db_session)
    _seed(db_session, org, action="widget:frobnicate", actor_label="alice@acme.test")
    _seed(db_session, org, action="gadget:tweak", actor_label="bob@acme.test")

    owner = _headers(_token(client, "owner@acme.test"))
    assert client.get(EVENTS, headers=owner, params={"q": "frobnicate"}).json()["total"] == 1
    assert client.get(EVENTS, headers=owner, params={"q": "ALICE"}).json()["total"] == 1
    assert client.get(EVENTS, headers=owner, params={"q": "nothing-like-this"}).json()["total"] == 0


def test_sorting_is_settable_and_an_unknown_sort_falls_back(client, db_session):
    org = _owner_org(client, db_session)
    for action in ("c:one", "a:two", "b:three"):
        _seed(db_session, org, action=action)

    owner = _headers(_token(client, "owner@acme.test"))
    ascending = client.get(
        EVENTS, headers=owner, params={"sort": "action", "order": "asc", "limit": 200}
    ).json()
    actions = [e["action"] for e in ascending["events"]]
    assert actions == sorted(actions)
    assert ascending["sort"] == "action"
    assert ascending["order"] == "asc"

    # A stale bookmark shows the log rather than a validation error.
    fallback = client.get(EVENTS, headers=owner, params={"sort": "; DROP TABLE"}).json()
    assert fallback["sort"] == "occurred_at"


def test_pagination_reports_the_true_total_and_never_repeats_a_row(client, db_session):
    org = _owner_org(client, db_session)
    for index in range(25):
        _seed(db_session, org, action=f"bulk:{index:02d}")

    owner = _headers(_token(client, "owner@acme.test"))
    seen: list[str] = []
    total = None
    for offset in (0, 10, 20, 30):
        page = client.get(EVENTS, headers=owner, params={"limit": 10, "offset": offset}).json()
        total = page["total"]
        seen.extend(e["id"] for e in page["events"])

    assert total >= 25
    # The property that matters: no id appears twice across the pages.
    assert len(seen) == len(set(seen))


def test_the_action_filter_options_come_from_the_data(client, db_session):
    org = _owner_org(client, db_session)
    _seed(db_session, org, action="zeta:last")

    body = client.get(EVENTS, headers=_headers(_token(client, "owner@acme.test"))).json()
    assert "zeta:last" in body["actions"]
    assert body["actions"] == sorted(body["actions"])


# --------------------------------------------------------------------------
# Record history
# --------------------------------------------------------------------------


def test_the_history_of_one_record_reads_oldest_first(client, db_session):
    org = _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")
    _signup(client, "member@acme.test")
    user = db_session.scalar(sa.select(User).where(User.email == "member@acme.test"))
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="viewer", status="active"))
    db_session.commit()

    client.patch(f"{MEMBERS}/{user.id}", headers=_headers(owner), json={"role": "analyst"})
    client.patch(f"{MEMBERS}/{user.id}", headers=_headers(owner), json={"role": "editor"})
    client.patch(f"{MEMBERS}/{user.id}", headers=_headers(owner), json={"status": "disabled"})

    body = client.get(f"{EVENTS}/history/user/{user.id}", headers=_headers(owner)).json()
    assert body["order"] == "asc"
    assert body["total"] == 3
    roles = [e["after"].get("role") for e in body["events"]]
    assert roles == ["analyst", "editor", "editor"]
    assert body["events"][-1]["after"]["status"] == "disabled"


def test_the_history_of_another_orgs_record_is_empty(client, db_session):
    _owner_org(client, db_session, "Acme")
    globex = _owner_org(client, db_session, "Globex")
    globex_owner = db_session.scalar(sa.select(User).where(User.email == "owner@globex.test"))

    body = client.get(
        f"{EVENTS}/history/user/{globex_owner.id}",
        headers=_headers(_token(client, "owner@acme.test")),
    ).json()
    assert body["total"] == 0
    del globex


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------


def test_one_orgs_audit_trail_is_invisible_to_another(client, db_session):
    acme = _owner_org(client, db_session, "Acme")
    _owner_org(client, db_session, "Globex")
    _seed(db_session, acme, action="acme:secret-thing")

    body = client.get(EVENTS, headers=_headers(_token(client, "owner@globex.test"))).json()
    assert all(e["action"] != "acme:secret-thing" for e in body["events"])


def test_no_filter_combination_reaches_another_org(client, db_session):
    acme = _owner_org(client, db_session, "Acme")
    _owner_org(client, db_session, "Globex")
    hidden = _seed(db_session, acme, action="acme:hidden", entity_type="thing")
    hidden_id = hidden.id

    globex_owner = _headers(_token(client, "owner@globex.test"))
    for params in (
        {"q": "acme"},
        {"action": "acme:"},
        {"entity_type": "thing"},
        {"limit": 200},
        {"sort": "action", "order": "asc", "limit": 200},
    ):
        body = client.get(EVENTS, headers=globex_owner, params=params).json()
        assert all(e["id"] != str(hidden_id) for e in body["events"]), params


# --------------------------------------------------------------------------
# Integrity
# --------------------------------------------------------------------------


def test_an_untouched_log_verifies_clean(client, db_session):
    _owner_org(client, db_session)
    body = client.get(
        f"{EVENTS}/integrity", headers=_headers(_token(client, "owner@acme.test"))
    ).json()
    assert body["ok"] is True
    assert body["altered"] == 0
    assert body["checked"] >= 1
    assert body["intact"] == body["checked"]


def test_an_edited_row_reports_itself_as_altered(client, db_session):
    org = _owner_org(client, db_session)
    event = _seed(db_session, org, action="member:update", after={"role": "viewer"})
    event_id = event.id

    # Exactly what an intruder with SQL access would do — and what the Postgres
    # trigger installed by migration 0018 refuses outright. SQLite has no such
    # trigger, which is what makes this test possible here.
    db_session.execute(
        sa.update(AuditEvent).where(AuditEvent.id == event_id).values(after={"role": "owner"})
    )
    db_session.commit()

    owner = _headers(_token(client, "owner@acme.test"))
    report = client.get(f"{EVENTS}/integrity", headers=owner).json()
    assert report["ok"] is False
    assert report["altered"] == 1
    assert str(event_id) in report["altered_ids"]

    listed = client.get(EVENTS, headers=owner, params={"action": "member:update"}).json()
    assert listed["events"][0]["integrity"] == "altered"


def test_a_row_from_before_hashing_is_unverifiable_not_intact(client, db_session):
    org = _owner_org(client, db_session)
    legacy = AuditEvent(
        occurred_at=datetime.now(UTC),
        org_id=org.id,
        actor_type="system",
        action="legacy:event",
        outcome="success",
    )
    db_session.add(legacy)
    db_session.commit()

    owner = _headers(_token(client, "owner@acme.test"))
    listed = client.get(EVENTS, headers=owner, params={"action": "legacy:"}).json()
    assert listed["events"][0]["integrity"] == "unverifiable"

    report = client.get(f"{EVENTS}/integrity", headers=owner).json()
    assert report["unverifiable"] == 1
    # An unverifiable row is not counted as a failure — crying wolf over rows
    # that predate the column would teach reviewers to ignore this number.
    assert report["ok"] is True


def test_the_hash_survives_a_database_round_trip(client, db_session):
    org = _owner_org(client, db_session)
    event = _seed(
        db_session,
        org,
        action="round:trip",
        entity_type="thing",
        entity_id=uuid.uuid4(),
        before={"a": 1, "b": [1, 2, {"c": "d"}]},
        after={"b": [1, 2, {"c": "e"}], "a": 1},
        detail={"nested": {"deep": True}},
    )
    event_id = event.id
    db_session.expunge_all()

    reloaded = db_session.get(AuditEvent, event_id)
    assert audit.verify_row(reloaded) is True


def test_the_request_id_is_returned_even_when_the_request_fails(client, db_session):
    """The id is most needed on the responses a user complains about.

    A 200 that carries a request id and a 401 that does not is the wrong way
    round: nobody quotes an identifier for a call that worked. This pins that
    the header survives the framework's own error paths — an auth rejection and
    a validation rejection, neither of which reaches a route function.
    """

    unauthorized = client.get(EVENTS)
    assert unauthorized.status_code == 401
    assert unauthorized.headers.get("x-request-id")

    unprocessable = client.get("/api/v1/invitations/short")
    assert unprocessable.status_code == 422
    assert unprocessable.headers.get("x-request-id")

    healthy = client.get("/healthz")
    assert healthy.headers.get("x-request-id")
    # Three distinct requests, three distinct ids — a constant would be useless.
    assert (
        len(
            {
                unauthorized.headers["x-request-id"],
                unprocessable.headers["x-request-id"],
                healthy.headers["x-request-id"],
            }
        )
        == 3
    )


def test_logging_out_is_recorded(client, db_session):
    """ "When did they leave?" is half of "were they here when this happened?".

    The event has to be written from the user read BEFORE the token is spent —
    afterwards there is nothing left to attribute it to.
    """

    _owner_org(client, db_session)
    login = client.post(LOGIN, json={"email": "owner@acme.test", "password": PASSWORD})
    owner = login.json()["access_token"]

    assert client.post("/api/v1/auth/logout").status_code == 204

    body = client.get(EVENTS, headers=_headers(owner), params={"action": "auth:logout"}).json()
    assert body["total"] == 1
    event = body["events"][0]
    assert event["actor_label"] == "owner@acme.test"
    assert event["outcome"] == "success"


def test_a_logout_with_a_junk_token_records_nothing(client, db_session):
    """Silence is the point: an event here would let the log probe token validity.

    Logout is an idempotent no-op that must never disclose whether the supplied
    token was ever real, and writing "somebody tried to log out with a bad
    token" would leak precisely that through the audit trail instead.
    """

    _owner_org(client, db_session)
    owner = _token(client, "owner@acme.test")

    # Clear first: the login above left a REAL refresh cookie on the client,
    # and setting a junk one under a misspelt name would leave the real one in
    # place — the test would then pass a legitimate logout off as a junk one.
    client.cookies.clear()
    client.cookies.set("yanki_refresh_token", "not-a-real-token")
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.cookies.clear()

    body = client.get(EVENTS, headers=_headers(owner), params={"action": "auth:logout"}).json()
    assert body["total"] == 0
