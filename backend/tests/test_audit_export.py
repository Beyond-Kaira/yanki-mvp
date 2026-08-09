"""CSV export on the audit log — and the export's own audit event (P7.9, §6).

The admin plan requires this and it had never been built. Three properties are
what make it more than a formatting change, and each has its own section below:

* it honours the **same filters** as the list, so a UI can export what is on
  screen rather than the whole trail;
* it carries the **integrity verdict** per row, so the file is evidence rather
  than a spreadsheet of claims;
* **exporting is itself audited**, because taking a copy of the compliance
  record out of the system is exactly the sort of action the record exists to
  remember.

It is also the first route where the audit spine records something *about the
audit spine*, which is worth one moment of care: the export event is written
after the rows are gathered, so it never appears inside its own export.
"""

from __future__ import annotations

import csv
import io
import uuid

import pytest
from sqlalchemy import select

from app.api.main import app
from app.db.models import AuditEvent
from app.services import audit
from app.services.tenancy import OrgContext

EXPORT_URL = "/api/v1/admin/audit-events/export.csv"


@pytest.fixture
def owner(client, db_session, signed_in):
    """A signed-in owner whose org already has a few events to export."""

    user, org = signed_in()
    context = OrgContext(org_id=org.id, user_id=user.id)
    for index in range(3):
        audit.emit(
            db_session,
            action="member:update",
            context=context,
            actor_type="user",
            actor_id=user.id,
            actor_label=user.email,
            entity_type="user",
            entity_id=user.id,
            before={"role": "viewer"},
            after={"role": f"editor-{index}"},
        )
    db_session.commit()
    return user, org


def _rows(response) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(response.text)))


def test_the_export_is_a_csv_attachment(client, owner) -> None:
    response = client.get(EXPORT_URL)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "audit-events.csv" in response.headers["content-disposition"]


def test_the_columns_are_fixed_and_ordered(client, owner) -> None:
    """A CSV whose columns move between exports is unusable to the thing that
    actually consumes it — a spreadsheet, or an auditor's script."""

    header = next(csv.reader(io.StringIO(client.get(EXPORT_URL).text)))

    assert header == [
        "occurred_at",
        "action",
        "outcome",
        "actor_type",
        "actor_label",
        "actor_id",
        "entity_type",
        "entity_id",
        "request_id",
        "record_hash",
        "integrity",
        "changed",
    ]


# ---------------------------------------------------------------------------
# The same filters as the list
# ---------------------------------------------------------------------------


def test_the_export_honours_the_action_filter(client, db_session, owner) -> None:
    """An export that ignored the filters would hand somebody the whole trail
    when they asked for one week of one actor — both less useful and more
    disclosure than they wanted."""

    user, org = owner
    audit.emit(
        db_session,
        action="invitation:create",
        context=OrgContext(org_id=org.id, user_id=user.id),
        actor_type="user",
        actor_id=user.id,
    )
    db_session.commit()

    rows = _rows(client.get(EXPORT_URL, params={"action": "invitation:"}))

    assert rows
    assert {row["action"] for row in rows} == {"invitation:create"}


def test_the_export_is_scoped_to_the_callers_organization(client, db_session, owner) -> None:
    """The one that would matter most if it were wrong. `org_id` comes from the
    caller's context and is never a parameter, so no combination of filters
    reaches another tenant."""

    user, _org = owner
    stranger_org = uuid.uuid4()
    audit.emit(
        db_session,
        action="member:update",
        context=OrgContext(org_id=stranger_org, user_id=uuid.uuid4()),
        actor_type="user",
        actor_label="stranger@elsewhere.test",
    )
    db_session.commit()

    rows = _rows(client.get(EXPORT_URL))

    assert "stranger@elsewhere.test" not in {row["actor_label"] for row in rows}


def test_an_unmatched_filter_exports_a_header_and_nothing_else(client, owner) -> None:
    """Not a 404 and not an error: "nothing matched" is a real answer, and a
    file with a header row is what a spreadsheet expects to receive."""

    response = client.get(EXPORT_URL, params={"action": "nothing:matches-this"})

    assert response.status_code == 200
    assert _rows(response) == []
    assert response.text.startswith("occurred_at,")


# ---------------------------------------------------------------------------
# The integrity verdict travels with the rows
# ---------------------------------------------------------------------------


def test_every_exported_row_carries_its_integrity_verdict(client, owner) -> None:
    rows = _rows(client.get(EXPORT_URL))

    assert rows
    assert {row["integrity"] for row in rows} == {"intact"}
    assert all(row["record_hash"] for row in rows)


def test_a_tampered_row_exports_as_altered(client, db_session, owner) -> None:
    """The property that makes the file evidence rather than a list of claims.
    The row is edited through the ORM — which SQLite permits and production's
    triggers do not — precisely so the *detection* can be tested without needing
    a way to defeat the database."""

    event = db_session.scalars(
        select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(1)
    ).first()
    assert event is not None
    event.actor_label = "someone-else@example.test"
    db_session.commit()

    rows = _rows(client.get(EXPORT_URL))
    altered = [item for item in rows if item["actor_label"] == "someone-else@example.test"]

    assert altered, "the edited row should still be exported"
    assert altered[0]["integrity"] == "altered"


def test_a_row_written_before_hashes_existed_is_unverifiable_not_altered(
    client, db_session, owner
) -> None:
    """Three answers, not two. Reporting a pre-`record_hash` row as *altered*
    cries wolf; reporting it as *intact* is a claim the data cannot support."""

    user, org = owner
    legacy = audit.emit(
        db_session,
        action="member:update",
        context=OrgContext(org_id=org.id, user_id=user.id),
        actor_type="user",
        actor_label="legacy@example.test",
    )
    assert legacy is not None
    legacy.record_hash = None
    db_session.commit()

    rows = _rows(client.get(EXPORT_URL))
    row = next(item for item in rows if item["actor_label"] == "legacy@example.test")

    assert row["integrity"] == "unverifiable"


def test_the_export_carries_the_redacted_diff_not_the_raw_payload(
    client, db_session, owner
) -> None:
    """Rows go through the same `_event_out` the list view uses, so nothing
    leaves in the file that the API would not already show."""

    user, org = owner
    audit.emit_change(
        db_session,
        action="member:update",
        context=OrgContext(org_id=org.id, user_id=user.id),
        actor_type="user",
        actor_label="diffed@example.test",
        before={"role": "viewer", "password_hash": "very-secret"},
        after={"role": "admin", "password_hash": "also-secret"},
    )
    db_session.commit()

    rows = _rows(client.get(EXPORT_URL))
    row = next(item for item in rows if item["actor_label"] == "diffed@example.test")

    assert '"role"' in row["changed"]
    assert "very-secret" not in row["changed"]
    assert "[redacted]" in row["changed"]


# ---------------------------------------------------------------------------
# Exporting is itself an event
# ---------------------------------------------------------------------------


def test_exporting_emits_an_audit_event(client, db_session, owner) -> None:
    """Somebody just took a copy of the compliance record out of the system.
    An audit log that cannot say who exported it is missing the event most
    likely to matter afterwards."""

    client.get(EXPORT_URL)
    db_session.expire_all()

    exports = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "audit:export")
    ).all()

    assert len(exports) == 1


def test_the_export_event_records_the_filters_and_the_count(client, db_session, owner) -> None:
    """ "What did they take?" is the question this event exists to answer, and
    an event that only said "an export happened" would not answer it."""

    client.get(EXPORT_URL, params={"action": "member:", "outcome": "success"})
    db_session.expire_all()

    event = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "audit:export"))
    assert event is not None
    detail = event.detail

    assert detail is not None
    assert detail["format"] == "csv"
    assert detail["rows"] >= 1
    assert detail["filters"] == {"action": "member:", "outcome": "success"}


def test_unset_filters_are_left_out_of_the_event(client, db_session, owner) -> None:
    """So the common unfiltered export does not bury the interesting one under
    nine empty fields."""

    client.get(EXPORT_URL)
    db_session.expire_all()

    event = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "audit:export"))
    assert event is not None
    detail = event.detail

    assert detail is not None
    assert detail["filters"] == {}


def test_the_export_event_is_not_inside_its_own_export(client, db_session, owner) -> None:
    """Written after the rows are gathered, deliberately. A record that contains
    the act of producing it is a small paradox and a real confusion for whoever
    reads the file."""

    rows = _rows(client.get(EXPORT_URL))

    assert "audit:export" not in {row["action"] for row in rows}
    # But it is there on the next one, which is what makes the first assertion
    # about ordering rather than about the event being missing.
    assert "audit:export" in {row["action"] for row in _rows(client.get(EXPORT_URL))}


def test_a_truncated_export_says_so_in_its_event(client, db_session, owner, monkeypatch) -> None:
    """An export capped at the ceiling may not be the whole answer, and whoever
    reads the event later should not have to infer that by comparing two
    numbers."""

    response = client.get(EXPORT_URL, params={"limit": 1})
    assert response.status_code == 200
    db_session.expire_all()

    event = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "audit:export"))
    assert event is not None
    detail = event.detail

    assert detail is not None
    assert detail["rows"] == 1
    assert detail["matched"] > 1
    assert detail["truncated"] is True


# ---------------------------------------------------------------------------
# Bounds and permission
# ---------------------------------------------------------------------------


def test_the_export_is_bounded(client, owner) -> None:
    """An unbounded export is a synchronous request holding a database
    connection open for a million rows. When an organization outgrows the
    ceiling the answer is an export artifact, not a bigger number."""

    assert client.get(EXPORT_URL, params={"limit": 50_000}).status_code == 422
    assert client.get(EXPORT_URL, params={"limit": 0}).status_code == 422


def test_the_export_needs_the_audit_read_permission(client, db_session, owner) -> None:
    """Same permission as reading the log, which is the honest mapping: this
    discloses exactly what the list route discloses, in a different container."""

    from app.api.auth_dependencies import get_current_user
    from app.db.models import Membership

    user, org = owner
    row = db_session.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.org_id == org.id)
    )
    assert row is not None
    row.role = "viewer"  # Viewer does not hold `audit:read`
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user

    assert client.get(EXPORT_URL).status_code == 403


def test_an_anonymous_caller_gets_401(client) -> None:
    assert client.get(EXPORT_URL).status_code == 401


def test_the_export_route_is_classified_in_the_leakage_census() -> None:
    """The census is the mechanism, so a new route proves it by being in it.
    This assertion exists so the two files fail together rather than one of them
    silently drifting."""

    from tests.test_cross_tenant_leakage import ORG

    assert ("GET", "/api/v1/admin/audit-events/export.csv") in ORG
