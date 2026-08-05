"""The audit spine — every mutating action, with before/after and no secrets.

One function does the work: :func:`emit`. Everything else here exists to make
it safe to call from anywhere.

Three properties the rest of the milestone depends on:

**Append-only.** Nothing in this module updates or deletes. The store is
write-and-read; an audit log that can be edited answers a weaker question than
the one it exists to answer.

**Redacted by construction, not by discipline.** :func:`redact` walks a payload
and replaces anything whose key looks like a credential. It is deliberately
key-name-based and deliberately over-eager: the cost of redacting a harmless
field is a less useful diff, and the cost of missing one is a password hash in a
table built to be exported. Those are not comparable, so this errs hard in one
direction.

**Never the reason a request fails.** :func:`emit` catches its own errors. An
audit write failing must not turn a successful password change into a 500 — the
change already happened, and the honest outcome is a logged warning about the
missing audit row rather than a lie to the user about the operation. That is a
real trade (a silently missing event) and it is recorded as tech-debt rather
than hidden: hardening it into an outbox belongs with M1's exit gate.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent
from app.services.tenancy import OrgContext

logger = logging.getLogger(__name__)

# Substrings that mark a value as a credential. Matched case-insensitively
# against the KEY, never the value — a value-based heuristic would both miss
# things and mangle ordinary text.
_SECRET_HINTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "session",
    "credential",
    "private",
    "signature",
    "hash",
    "salt",
    "otp",
    "mfa",
    "backup_code",
)

REDACTED = "[redacted]"

# Depth and breadth caps. An audit row is evidence, not a backup: a runaway
# nested payload would make the table expensive and the diff unreadable.
_MAX_DEPTH = 6
_MAX_ITEMS = 200
_MAX_STRING = 2000


def looks_secret(key: str) -> bool:
    lowered = (key or "").lower()
    return any(hint in lowered for hint in _SECRET_HINTS)


def redact(value: Any, *, _depth: int = 0) -> Any:
    """Return a copy safe to store, with credential-shaped fields replaced.

    Over-eager on purpose — see the module docstring. ``password_hash``,
    ``jwt_secret_key``, ``refresh_jti_hash`` and anything else whose key reads
    like a credential becomes ``[redacted]`` regardless of what it holds.
    """

    if _depth >= _MAX_DEPTH:
        return "[truncated]"

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                out["[truncated]"] = f"{len(value) - _MAX_ITEMS} more field(s)"
                break
            out[str(key)] = REDACTED if looks_secret(str(key)) else redact(item, _depth=_depth + 1)
        return out

    if isinstance(value, (list, tuple)):
        return [redact(item, _depth=_depth + 1) for item in list(value)[:_MAX_ITEMS]]

    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING else value[:_MAX_STRING] + "…"

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)

    return str(value)[:_MAX_STRING]


def diff(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    """Only the keys that actually changed, both sides redacted.

    Storing whole objects would bury the one field that moved and would make
    every event carry every column forever. A diff is what a reviewer reads.
    """

    before = before or {}
    after = after or {}
    changed = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old != new:
            changed[key] = {
                "from": REDACTED if looks_secret(key) else redact(old),
                "to": REDACTED if looks_secret(key) else redact(new),
            }
    return changed


def emit(
    session: Session,
    *,
    action: str,
    context: OrgContext | None = None,
    actor_type: str = "system",
    actor_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    outcome: str = "success",
    ip_hash: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent | None:
    """Record one auditable action. Never raises.

    ``action`` is a ``resource:action`` string (``auth:login``,
    ``project:create``, ``member:role_change``) so the taxonomy extends without
    a schema change — the same reasoning that keeps roles as text in P7.2.

    Returns the row, or ``None`` if the write failed. Adds to the session
    without committing: the event belongs in the caller's transaction, so an
    action that rolls back does not leave an audit row claiming it happened.
    """

    try:
        event = AuditEvent(
            occurred_at=datetime.now(UTC),
            org_id=context.org_id if context else None,
            workspace_id=context.default_workspace_id if context else None,
            actor_type=actor_type,
            actor_id=actor_id if actor_id is not None else (context.user_id if context else None),
            actor_label=actor_label,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=redact(before) if before is not None else None,
            after=redact(after) if after is not None else None,
            ip_hash=ip_hash,
            user_agent=(user_agent or None) and str(user_agent)[:500],
            request_id=request_id,
            outcome=outcome,
            detail=redact(detail) if detail is not None else None,
        )
        session.add(event)
        session.flush()
        return event
    except Exception:  # noqa: BLE001 - see the module docstring
        # The action already happened. Failing the request now would be a lie
        # about the operation; a missing event is the lesser, and louder, harm.
        logger.warning("audit event %s could not be recorded", action, exc_info=True)
        return None


def emit_change(
    session: Session,
    *,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    **kwargs: Any,
) -> AuditEvent | None:
    """:func:`emit` with a computed before/after diff in ``detail``."""

    changed = diff(before, after)
    detail = dict(kwargs.pop("detail", None) or {})
    detail["changed"] = changed
    return emit(session, action=action, before=before, after=after, detail=detail, **kwargs)


def events_for_org(
    session: Session,
    *,
    org_id: uuid.UUID,
    limit: int = 100,
    action: str | None = None,
) -> list[AuditEvent]:
    """The org's audit trail, newest first. Org-scoped like everything else."""

    statement = select(AuditEvent).where(AuditEvent.org_id == org_id)
    if action:
        statement = statement.where(AuditEvent.action == action)
    return list(session.scalars(statement.order_by(AuditEvent.occurred_at.desc()).limit(limit)))


def entity_timeline(
    session: Session, *, entity_type: str, entity_id: uuid.UUID, limit: int = 100
) -> list[AuditEvent]:
    """Everything that ever touched one record — the admin UI's timeline view."""

    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.occurred_at.desc())
            .limit(limit)
        )
    )
