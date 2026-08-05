"""The audit spine (P7.3) — mostly a test that secrets never reach the store.

An audit table is built to be read, exported, and eventually shown to auditors
and customers. That makes it the worst possible place for a credential to
land, and the most likely — because the natural way to write "record what
changed" is to dump the object, and objects here carry ``password_hash`` and
``refresh_jti_hash``.

So the redaction tests are the point of this module, and they are written as
"this must not appear" rather than "this should appear".
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.db.models import AuditEvent, User
from app.services import audit
from app.services.auth import authenticate_user, create_user
from app.services.tenancy import OrgContext

# --------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "Password",
        "password_hash",
        "jwt_secret_key",
        "api_key",
        "apiKey",
        "authorization",
        "refresh_jti_hash",
        "session_token",
        "ip_hash_salt",
        "mfa_secret",
        "backup_codes",
        "private_key",
    ],
)
def test_credential_shaped_keys_are_redacted(key):
    assert audit.redact({key: "super-secret-value"})[key] == audit.REDACTED


def test_ordinary_fields_survive():
    payload = {"email": "a@b.example", "name": "Acme", "page_limit": 10}
    assert audit.redact(payload) == payload


def test_redaction_reaches_nested_structures():
    payload = {
        "user": {"email": "a@b.example", "password_hash": "argon2..."},
        "keys": [{"api_key": "sk-live-123"}],
    }
    result = audit.redact(payload)
    assert result["user"]["password_hash"] == audit.REDACTED
    assert result["user"]["email"] == "a@b.example"
    assert result["keys"][0]["api_key"] == audit.REDACTED


def test_a_deeply_nested_payload_is_truncated_not_walked_forever():
    payload: dict = {"a": {}}
    node = payload["a"]
    for _ in range(20):
        node["a"] = {}
        node = node["a"]
    # Terminates, and says that it did.
    assert "[truncated]" in str(audit.redact(payload))


def test_long_strings_are_capped():
    result = audit.redact({"note": "x" * 5000})
    assert len(result["note"]) < 5000


def test_uuid_and_datetime_become_strings():
    value = uuid.uuid4()
    assert audit.redact({"id": value})["id"] == str(value)


# --------------------------------------------------------------------------
# Diffing
# --------------------------------------------------------------------------


def test_diff_reports_only_what_changed():
    changed = audit.diff({"a": 1, "b": 2}, {"a": 1, "b": 3})
    assert list(changed) == ["b"]
    assert changed["b"] == {"from": 2, "to": 3}


def test_diff_reports_that_a_secret_changed_without_revealing_either_value():
    changed = audit.diff({"password_hash": "old"}, {"password_hash": "new"})
    assert changed["password_hash"] == {"from": audit.REDACTED, "to": audit.REDACTED}


def test_diff_covers_added_and_removed_keys():
    changed = audit.diff({"a": 1}, {"b": 2})
    assert set(changed) == {"a", "b"}


# --------------------------------------------------------------------------
# emit
# --------------------------------------------------------------------------


def test_emit_records_an_event(db_session):
    context = OrgContext(org_id=uuid.uuid4(), user_id=uuid.uuid4())
    event = audit.emit(
        db_session,
        action="project:create",
        context=context,
        actor_type="user",
        entity_type="seo_project",
        entity_id=uuid.uuid4(),
        after={"name": "Acme"},
    )
    db_session.commit()

    assert event is not None
    stored = db_session.get(AuditEvent, event.id)
    assert stored.action == "project:create"
    assert stored.org_id == context.org_id
    assert stored.actor_id == context.user_id
    assert stored.outcome == "success"
    assert stored.after == {"name": "Acme"}


def test_emit_never_raises_even_when_the_write_fails(db_session, monkeypatch):
    """An audit failure must not turn a successful action into a 500."""

    def _explode(*args, **kwargs):
        raise RuntimeError("table is on fire")

    monkeypatch.setattr(db_session, "add", _explode)
    assert audit.emit(db_session, action="project:create") is None


def test_emit_redacts_before_storing(db_session):
    event = audit.emit(
        db_session,
        action="user:update",
        before={"email": "a@b.example", "password_hash": "argon2-old"},
        after={"email": "a@b.example", "password_hash": "argon2-new"},
    )
    db_session.commit()

    assert event is not None
    assert event.before["password_hash"] == audit.REDACTED
    assert event.after["password_hash"] == audit.REDACTED
    assert "argon2" not in str(event.before) + str(event.after)


def test_emit_change_attaches_a_diff(db_session):
    event = audit.emit_change(
        db_session,
        action="project:update",
        before={"name": "Old", "domain": "same.example"},
        after={"name": "New", "domain": "same.example"},
    )
    db_session.commit()

    assert event is not None
    assert list(event.detail["changed"]) == ["name"]
    assert event.detail["changed"]["name"] == {"from": "Old", "to": "New"}


# --------------------------------------------------------------------------
# The wired call sites
# --------------------------------------------------------------------------


def test_signup_is_audited(db_session):
    user = create_user(db_session, email="new@example.com", password="hunter22")

    event = db_session.scalar(sa.select(AuditEvent).where(AuditEvent.action == "auth:signup"))
    assert event is not None
    assert event.actor_id == user.id
    assert event.entity_type == "user"
    assert event.after["email"] == "new@example.com"
    assert "org_slug" in event.after


def test_a_successful_login_is_audited(db_session):
    create_user(db_session, email="who@example.com", password="hunter22")
    authenticate_user(db_session, email="who@example.com", password="hunter22")

    events = db_session.scalars(
        sa.select(AuditEvent).where(AuditEvent.action == "auth:login")
    ).all()
    assert len(events) == 1
    assert events[0].outcome == "success"


def test_a_failed_login_is_audited_as_denied_without_the_password(db_session):
    create_user(db_session, email="who@example.com", password="hunter22")
    assert authenticate_user(db_session, email="who@example.com", password="wrong") is None

    event = db_session.scalar(sa.select(AuditEvent).where(AuditEvent.outcome == "denied"))
    assert event is not None
    assert event.action == "auth:login"
    assert event.actor_label == "who@example.com"
    assert "wrong" not in str(event.detail) + str(event.before) + str(event.after)


def test_an_unknown_email_login_is_audited_as_anonymous(db_session):
    assert authenticate_user(db_session, email="ghost@example.com", password="x") is None
    event = db_session.scalar(sa.select(AuditEvent))
    assert event is not None
    assert event.actor_type == "anonymous"
    assert event.actor_id is None


def test_no_audit_row_survives_a_rolled_back_signup(db_session):
    """The event lives in the caller's transaction, so it cannot outlive it."""

    audit.emit(db_session, action="auth:signup", after={"email": "ghost@example.com"})
    db_session.rollback()
    assert db_session.scalar(sa.select(sa.func.count()).select_from(AuditEvent)) == 0


# --------------------------------------------------------------------------
# Reading it back
# --------------------------------------------------------------------------


def test_events_are_org_scoped(db_session):
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    audit.emit(db_session, action="project:create", context=OrgContext(org_id=org_a))
    audit.emit(db_session, action="project:create", context=OrgContext(org_id=org_b))
    db_session.commit()

    assert audit.search_events(db_session, audit.EventQuery(org_id=org_a)).total == 1
    assert audit.search_events(db_session, audit.EventQuery(org_id=org_b)).total == 1


def test_entity_timeline_collects_everything_that_touched_one_record(db_session):
    entity = uuid.uuid4()
    for action in ("project:create", "project:update", "project:delete"):
        audit.emit(db_session, action=action, entity_type="seo_project", entity_id=entity)
    audit.emit(
        db_session, action="project:create", entity_type="seo_project", entity_id=uuid.uuid4()
    )
    db_session.commit()

    timeline = audit.search_events(
        db_session, audit.EventQuery(entity_type="seo_project", entity_id=entity)
    )
    assert timeline.total == 3
    assert {e.action for e in timeline.events} == {
        "project:create",
        "project:update",
        "project:delete",
    }


def test_the_store_holds_no_password_material_after_a_full_signup_and_login(db_session):
    """The end-to-end version of the property this module exists for."""

    create_user(db_session, email="real@example.com", password="correct-horse-battery")
    authenticate_user(db_session, email="real@example.com", password="wrong-one")
    authenticate_user(db_session, email="real@example.com", password="correct-horse-battery")
    db_session.commit()

    blob = " ".join(
        f"{e.before} {e.after} {e.detail}" for e in db_session.scalars(sa.select(AuditEvent))
    )
    assert "correct-horse-battery" not in blob
    assert "wrong-one" not in blob
    assert "argon2" not in blob
    user = db_session.scalar(sa.select(User).where(User.email == "real@example.com"))
    assert user is not None
    assert user.password_hash not in blob
