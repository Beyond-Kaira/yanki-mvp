"""The mutating paths the audit spine used to skip (tech-debt #71).

M1 promises "every mutating action emits an audit event". Six paths did not:
refresh-token reuse detection, competitor track/untrack, the checker submit and
its lead gate, and the waitlist. A seventh — a quota refusal — is not a mutation
at all and is audited anyway, for the reason `quota._record_refusal` gives.

The suite is organized around two questions, because a coverage claim needs
both answered:

* **Does the event exist, and does it say something useful?** A row with the
  right ``action`` and nothing else in it is not coverage; each test asserts on
  the field a reader would actually go looking for.
* **Is the silence deliberate where we chose silence?** Successful token
  rotation, an ordinary expired refresh, and a duplicate waitlist signup emit
  nothing on purpose. Those are asserted too — an intentional gap that nobody
  wrote a test for is indistinguishable from one that was forgotten, which is
  how #71 came to exist in the first place.
"""

from __future__ import annotations

import uuid
from urllib.parse import urlsplit

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import Analysis, AuditEvent, User
from app.services import billing
from app.services.auth import hash_password
from app.services.auth_sessions import (
    RefreshTokenReuseDetectedError,
    rotate_refresh_session,
    start_refresh_session,
)
from app.services.tenancy import provision_personal_org


@pytest.fixture
def token_settings() -> Settings:
    return Settings(
        jwt_secret_key=SecretStr("a" * 64),
        jwt_issuer="test-yanki-api",
        jwt_audience="test-yanki-web",
        jwt_access_token_minutes=15,
        jwt_refresh_token_days=30,
        jwt_clock_skew_seconds=0,
    )


def _events(session: Session, action: str) -> list[AuditEvent]:
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.occurred_at)
        )
    )


def _user_with_org(session: Session, email: str = "owner@example.test") -> User:
    user = User(email=email, password_hash=hash_password("correct-horse"))
    session.add(user)
    session.flush()
    provision_personal_org(session, user)
    session.commit()
    return user


# ---------------------------------------------------------------------------
# Refresh-token reuse — the sharp edge of #71
# ---------------------------------------------------------------------------


def test_refresh_token_reuse_is_audited(db_session: Session, token_settings: Settings) -> None:
    """The event that revokes a sign-in for suspected theft, and recorded nothing.

    This is the whole point of the item: reuse detection signs somebody out
    because it believes their token was stolen, and a security review that came
    looking for it found an empty table.
    """

    user = _user_with_org(db_session)
    started = start_refresh_session(db_session, user_id=user.id, settings=token_settings)
    rotate_refresh_session(
        db_session, refresh_token=started.refresh_token.value, settings=token_settings
    )

    with pytest.raises(RefreshTokenReuseDetectedError):
        rotate_refresh_session(
            db_session, refresh_token=started.refresh_token.value, settings=token_settings
        )

    db_session.expire_all()
    events = _events(db_session, "auth:refresh_reuse")
    assert len(events) == 1
    event = events[0]
    assert event.outcome == "denied"
    assert event.actor_id == user.id
    assert event.actor_label == user.email
    # Attributed to the user's organization, not NULL. An event with a NULL org
    # is invisible in the Admin Panel's log, which is the only place anyone
    # would look for it.
    assert event.org_id is not None
    assert event.detail is not None
    assert event.detail["reason"] == "refresh_token_reuse"
    assert event.detail["revoked_family"] == str(started.family_id)


def test_the_reuse_event_survives_the_error_that_follows_it(
    db_session: Session, token_settings: Settings
) -> None:
    """Committed with the revocation, not after it.

    `rotate_refresh_session` commits the family revocation and then raises. If
    the event were emitted after that commit there would be a window in which
    someone was signed out with nothing recorded — and if it were emitted into a
    transaction that the raise unwound, there would be no record at all. A fresh
    session proves it is actually on disk rather than pending in the caller's.
    """

    user = _user_with_org(db_session)
    started = start_refresh_session(db_session, user_id=user.id, settings=token_settings)
    rotate_refresh_session(
        db_session, refresh_token=started.refresh_token.value, settings=token_settings
    )
    with pytest.raises(RefreshTokenReuseDetectedError):
        rotate_refresh_session(
            db_session, refresh_token=started.refresh_token.value, settings=token_settings
        )

    db_session.rollback()
    assert len(_events(db_session, "auth:refresh_reuse")) == 1


def test_the_family_id_is_not_redacted_out_of_the_event(
    db_session: Session, token_settings: Settings
) -> None:
    """The regression this key name exists to avoid.

    `redact()` blanks any payload key containing "session", so the obvious names
    — `session_id`, `family_session` — would store "[redacted]" and lose the one
    field that says *which* sign-in was killed. Named `revoked_family` for that
    reason, and asserted here so a well-meaning rename cannot quietly re-break it.
    """

    user = _user_with_org(db_session)
    started = start_refresh_session(db_session, user_id=user.id, settings=token_settings)
    rotate_refresh_session(
        db_session, refresh_token=started.refresh_token.value, settings=token_settings
    )
    with pytest.raises(RefreshTokenReuseDetectedError):
        rotate_refresh_session(
            db_session, refresh_token=started.refresh_token.value, settings=token_settings
        )

    db_session.expire_all()
    detail = _events(db_session, "auth:refresh_reuse")[0].detail
    assert detail is not None
    assert detail["revoked_family"] != "[redacted]"
    assert uuid.UUID(detail["revoked_family"]) == started.family_id


def test_an_ordinary_rotation_is_deliberately_not_audited(
    db_session: Session, token_settings: Settings
) -> None:
    """Silence on purpose: this fires four times an hour per signed-in device.

    Auditing it would bury every real event under heartbeat rows. Asserted so
    the choice reads as a decision rather than an oversight.
    """

    user = _user_with_org(db_session)
    started = start_refresh_session(db_session, user_id=user.id, settings=token_settings)
    rotate_refresh_session(
        db_session, refresh_token=started.refresh_token.value, settings=token_settings
    )

    db_session.expire_all()
    assert _events(db_session, "auth:refresh") == []
    assert _events(db_session, "auth:refresh_reuse") == []


# ---------------------------------------------------------------------------
# Competitor tracking — a spending decision with no record
# ---------------------------------------------------------------------------


def _project_for(client, signed_in, db_session):
    """A signed-in org with one SEO project, which competitors hang off."""

    user, org = signed_in(plan_key="enterprise")
    response = client.post("/api/v1/seo-projects", json={"domain": "example.com"})
    assert response.status_code == 201, response.text
    return user, org, uuid.UUID(response.json()["id"])


def test_tracking_a_competitor_is_audited(client, db_session, signed_in, monkeypatch) -> None:
    monkeypatch.setenv("BACKLINKS_ENABLED", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        user, org, project_id = _project_for(client, signed_in, db_session)
        response = client.post(
            f"/api/v1/seo-projects/{project_id}/backlinks/competitors",
            json={"domain": "rival.example", "label": "Rival"},
        )
        assert response.status_code == 201, response.text
    finally:
        get_settings.cache_clear()

    db_session.expire_all()
    events = _events(db_session, "backlink:competitor_track")
    assert len(events) == 1
    assert events[0].org_id == org.id
    assert events[0].actor_id == user.id
    assert events[0].after is not None
    assert events[0].after["competitor_domain"] == "rival.example"


def test_untracking_a_competitor_records_what_it_removed(
    client, db_session, signed_in, monkeypatch
) -> None:
    """The removal names the domain, which is only possible because the service
    reads it before the delete — after it there is nothing left to name."""

    monkeypatch.setenv("BACKLINKS_ENABLED", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        _user, org, project_id = _project_for(client, signed_in, db_session)
        created = client.post(
            f"/api/v1/seo-projects/{project_id}/backlinks/competitors",
            json={"domain": "rival.example"},
        )
        competitor_id = created.json()["id"]
        removed = client.delete(
            f"/api/v1/seo-projects/{project_id}/backlinks/competitors/{competitor_id}"
        )
        assert removed.status_code == 204, removed.text
    finally:
        get_settings.cache_clear()

    db_session.expire_all()
    events = _events(db_session, "backlink:competitor_untrack")
    assert len(events) == 1
    assert events[0].org_id == org.id
    assert events[0].before is not None
    assert events[0].before["competitor_domain"] == "rival.example"


# ---------------------------------------------------------------------------
# The anonymous surface — money spent by nobody, and PII we must not copy
# ---------------------------------------------------------------------------


def test_a_fresh_checker_run_is_audited_as_a_cache_miss(client, db_session, monkeypatch) -> None:
    """A miss is an LLM bill; the event is what lets the log explain the invoice."""

    monkeypatch.setenv("CHECKER_ENABLED", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/v1/checker",
            json={"brand": "Acme", "category": "widgets", "lang": "en"},
        )
        assert response.status_code == 202, response.text
    finally:
        get_settings.cache_clear()

    db_session.expire_all()
    events = _events(db_session, "checker:submit")
    assert len(events) == 1
    assert events[0].actor_type == "anonymous"
    assert events[0].org_id is None
    assert events[0].detail is not None
    assert events[0].detail["cache_hit"] is False
    assert events[0].after is not None
    assert events[0].after["brand"] == "acme"


def test_a_cached_checker_run_is_audited_as_a_hit(client, db_session, monkeypatch) -> None:
    """Both are recorded so "every mutating path emits" stays literally true —
    a cache hit still writes a submission row — and `cache_hit` is what tells
    the two apart when somebody asks why the bill moved."""

    done = Analysis(
        url="checker://acme/widgets",
        status="done",
        kind="checker",
        brand="acme",
        category="widgets",
        lang="en",
    )
    db_session.add(done)
    db_session.commit()

    monkeypatch.setenv("CHECKER_ENABLED", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/v1/checker",
            json={"brand": "Acme", "category": "widgets", "lang": "en"},
        )
        assert response.status_code == 202, response.text
    finally:
        get_settings.cache_clear()

    db_session.expire_all()
    events = _events(db_session, "checker:submit")
    assert len(events) == 1
    assert events[0].detail is not None
    assert events[0].detail["cache_hit"] is True


def test_a_refused_checker_submit_records_nothing(client, db_session, monkeypatch) -> None:
    """The kill switch parks the request before anything is created, so there is
    no mutation to audit — and auditing the attempt would hand an unauthenticated
    endpoint a way to write rows into an append-only table."""

    monkeypatch.setenv("CHECKER_ENABLED", "0")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/v1/checker",
            json={"brand": "Acme", "category": "widgets", "lang": "en"},
        )
        assert response.status_code == 503
    finally:
        get_settings.cache_clear()

    db_session.expire_all()
    assert _events(db_session, "checker:submit") == []


def test_the_lead_event_does_not_carry_the_email(client, db_session, monkeypatch) -> None:
    """The load-bearing PII decision.

    `audit_events` is append-only by database trigger — a row written here can
    never be deleted through the application. Copying an address in would put the
    erasure path in permanent conflict with the integrity guarantee, so the event
    keeps the reference and drops the value.
    """

    monkeypatch.setenv("CHECKER_ENABLED", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        submitted = client.post(
            "/api/v1/checker",
            json={"brand": "Acme", "category": "widgets", "lang": "en"},
        ).json()
        response = client.post(
            "/api/v1/checker/leads",
            json={"submission_id": submitted["submission_id"], "email": "lead@example.test"},
        )
        assert response.status_code == 202, response.text
    finally:
        get_settings.cache_clear()

    db_session.expire_all()
    events = _events(db_session, "checker:lead")
    assert len(events) == 1
    assert events[0].entity_id == uuid.UUID(submitted["submission_id"])
    assert "lead@example.test" not in str(events[0].detail) + str(events[0].after)


def test_a_waitlist_signup_is_audited_without_the_address(client, db_session) -> None:
    response = client.post("/api/v1/waitlist", json={"email": "someone@example.test"})
    assert response.status_code == 202

    db_session.expire_all()
    events = _events(db_session, "waitlist:signup")
    assert len(events) == 1
    assert events[0].actor_type == "anonymous"
    assert events[0].entity_type == "waitlist_signup"
    assert "someone@example.test" not in str(events[0].detail) + str(events[0].after)


def test_a_duplicate_waitlist_signup_writes_no_event(client, db_session) -> None:
    """No row was inserted, so there is no mutation to record — and recording it
    would put "this address is already on the list" into a table, which is the
    enumeration answer this endpoint's whole design refuses to give."""

    client.post("/api/v1/waitlist", json={"email": "someone@example.test"})
    client.post("/api/v1/waitlist", json={"email": "someone@example.test"})

    db_session.expire_all()
    assert len(_events(db_session, "waitlist:signup")) == 1


# ---------------------------------------------------------------------------
# Quota refusals — the billing half
# ---------------------------------------------------------------------------


def _pin(**overrides) -> None:
    """Lift the per-IP rate limit out of the way, as `test_quota_enforcement` does.

    The rate limiter and the plan quota both answer **429** and both default to
    five, so on stock settings the sixth submit is refused by whichever check
    runs first — and the first draft of this file was silently asserting on the
    rate limiter, which emits nothing. Getting a 429 is not evidence that the
    quota refused.
    """

    defaults: dict[str, object] = {
        "analyses_rate_limit_per_ip_hour": 1000,
        "analyses_daily_cap": 1000,
    }
    defaults.update(overrides)
    app.dependency_overrides[get_settings] = lambda: Settings(**defaults)


@pytest.fixture
def pinned():
    _pin()
    yield _pin
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def resolvable_domains(monkeypatch):
    """Let `*.test` through the SSRF guard, which otherwise resolves the host."""

    from app.api import seo_project_routes

    real_guard = seo_project_routes.is_public_url

    def guard(url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return True if host.endswith(".test") else real_guard(url)

    monkeypatch.setattr(seo_project_routes, "is_public_url", guard)


def test_a_quota_refusal_is_audited(client, db_session, signed_in, pinned) -> None:
    """Session 25 made every organization Free by default, so a refusal is now
    the likeliest thing to happen to a live user — and it was recorded nowhere."""

    user, org = signed_in()  # no subscription: falls back to Free
    limit = billing.limit_for(db_session, org.id, billing.METRIC_ANALYSES)
    assert limit is not None

    for index in range(limit):
        accepted = client.post("/api/v1/analyses", json={"url": f"https://example.com/{index}"})
        assert accepted.status_code == 202, accepted.text

    refused = client.post("/api/v1/analyses", json={"url": "https://example.com/over"})
    assert refused.status_code == 429
    # The body distinguishes it from the rate limiter's 429, which is the whole
    # reason the pin above exists.
    assert refused.json()["metric"] == billing.METRIC_ANALYSES

    db_session.expire_all()
    events = _events(db_session, "billing:quota_denied")
    assert len(events) == 1
    assert events[0].outcome == "denied"
    assert events[0].org_id == org.id
    assert events[0].actor_id == user.id
    assert events[0].detail is not None
    assert events[0].detail["metric"] == billing.METRIC_ANALYSES
    assert events[0].detail["limit"] == limit


def test_the_refusal_event_does_not_charge_the_allowance(
    client, db_session, signed_in, pinned
) -> None:
    """`_record_refusal` commits, and this is the invariant that makes that safe:
    the quota check raises *before* it writes, so the only thing in the
    transaction being committed is the event itself. A refusal that also spent a
    unit would be the worst possible bug in a billing gate."""

    _user, org = signed_in()
    limit = billing.limit_for(db_session, org.id, billing.METRIC_ANALYSES)
    assert limit is not None

    for index in range(limit):
        client.post("/api/v1/analyses", json={"url": f"https://example.com/{index}"})
    client.post("/api/v1/analyses", json={"url": "https://example.com/over"})

    db_session.expire_all()
    assert billing.usage(db_session, org.id, billing.METRIC_ANALYSES) == limit


def test_a_refusal_under_a_disabled_kill_switch_is_not_audited(
    client, db_session, signed_in, pinned
) -> None:
    """With enforcement off nothing refuses, so nothing is recorded. The switch
    turns the whole gate off, not just its arithmetic."""

    pinned(quota_enforcement_enabled=False)
    _user, org = signed_in()
    limit = billing.limit_for(db_session, org.id, billing.METRIC_ANALYSES)
    assert limit is not None
    for index in range(limit + 2):
        response = client.post("/api/v1/analyses", json={"url": f"https://example.com/{index}"})
        assert response.status_code == 202, response.text

    db_session.expire_all()
    assert _events(db_session, "billing:quota_denied") == []


def test_a_project_stock_refusal_is_audited(
    client, db_session, signed_in, pinned, resolvable_domains
) -> None:
    """The stock metric refuses through a different function (`check_stock`), so
    it needs its own coverage — a gate audited on one of its two entrances is a
    gate that reports half of what it does."""

    _user, org = signed_in()
    limit = billing.limit_for(db_session, org.id, billing.METRIC_PROJECTS)
    assert limit is not None

    for index in range(limit):
        created = client.post("/api/v1/seo-projects", json={"domain": f"example{index}.test"})
        assert created.status_code == 201, created.text

    refused = client.post("/api/v1/seo-projects", json={"domain": "over-the-limit.test"})
    assert refused.status_code == 429

    db_session.expire_all()
    events = _events(db_session, "billing:quota_denied")
    assert len(events) == 1
    assert events[0].detail is not None
    assert events[0].detail["metric"] == billing.METRIC_PROJECTS


# ---------------------------------------------------------------------------
# The claim this whole file is evidence for
# ---------------------------------------------------------------------------


def test_every_new_event_verifies_its_own_hash(client, db_session, signed_in) -> None:
    """Tamper-evidence is a property of the row, so a new emit site that
    constructed its payload wrongly would show up as an unverifiable row rather
    than as a failing assertion anywhere else."""

    from app.services import audit

    client.post("/api/v1/waitlist", json={"email": "someone@example.test"})
    _user, org = signed_in()
    limit = billing.limit_for(db_session, org.id, billing.METRIC_ANALYSES)
    assert limit is not None
    for index in range(limit + 1):
        client.post("/api/v1/analyses", json={"url": f"https://example.com/{index}"})

    db_session.expire_all()
    report = audit.verify_integrity(db_session)
    assert report.checked > 0
    assert report.altered == 0
    assert report.unverifiable == 0


def test_the_analysis_submit_path_still_emits_its_own_event(client, db_session, signed_in) -> None:
    """A guard on the refusal work: adding the denial event must not have
    displaced the success event that session 25 added on the same path."""

    _user, org = signed_in(plan_key="enterprise")
    accepted = client.post("/api/v1/analyses", json={"url": "https://example.com"})
    assert accepted.status_code == 202

    db_session.expire_all()
    events = _events(db_session, "analysis:create")
    assert len(events) == 1
    assert events[0].org_id == org.id


def test_an_old_event_written_before_a_window_is_untouched(db_session: Session) -> None:
    """The store is append-only: nothing added in this change updates a row.

    Cheap to assert and worth asserting, because six new emit sites is six new
    chances for one of them to have reached for an UPDATE.
    """

    from app.services import audit

    stale = audit.emit(db_session, action="waitlist:signup", entity_type="waitlist_signup")
    assert stale is not None
    db_session.commit()
    original_hash = stale.record_hash
    original_time = stale.occurred_at

    audit.emit(db_session, action="waitlist:signup", entity_type="waitlist_signup")
    db_session.commit()
    db_session.expire_all()

    reread = db_session.get(AuditEvent, stale.id)
    assert reread is not None
    assert reread.record_hash == original_hash
    # Compared without timezone metadata: SQLite hands back a naive value for
    # the same instant Postgres returns as aware, and the point here is that the
    # row did not move, not which driver served it.
    assert reread.occurred_at.replace(tzinfo=None) == original_time.replace(tzinfo=None)
    assert audit.verify_row(reread) is True
