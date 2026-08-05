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

**Tamper-evident, within stated limits.** Every row carries
:func:`compute_record_hash` over its own content, and migration 0018 installs
two Postgres triggers — one raising on UPDATE or DELETE, and a separate
statement-level one raising on TRUNCATE, which a row-level trigger does not
catch. Together those make an edit detectable (:func:`verify_row`) and a
deletion impossible through the database's own rules. What they do NOT do is
survive a superuser who drops the triggers first — see the ``record_hash``
column comment for why a hash chain was not the answer, and
:func:`verify_integrity` for what the admin surface can actually prove.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent
from app.request_context import current_request_info
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


# The fields the record hash covers. Everything an investigator would read, and
# nothing that is derived from them — a hash over its own column would be
# self-referential, and one over a mutable field would break for a legitimate
# reason and teach reviewers to ignore failures.
_HASHED_FIELDS = (
    "id",
    "occurred_at",
    "org_id",
    "workspace_id",
    "actor_type",
    "actor_id",
    "actor_label",
    "action",
    "entity_type",
    "entity_id",
    "before",
    "after",
    "ip_hash",
    "user_agent",
    "request_id",
    "outcome",
    "detail",
)


def _canonical(value: Any) -> Any:
    """A JSON-stable view of one field, so the same row always hashes the same."""

    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        # Normalized to aware UTC first: SQLite hands back naive datetimes for
        # the same instant Postgres returns as aware, and a hash that depends on
        # the driver would fail verification on the wrong database rather than
        # on a tampered row.
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).isoformat()
    return value


def compute_record_hash(event: AuditEvent) -> str:
    """SHA-256 over the row's audited content, as canonical JSON.

    ``sort_keys`` and a fixed field order make the digest depend on the values
    and nothing else — not on dict insertion order, not on the JSON column's
    round-trip, not on which database served the read.
    """

    payload = {field: _canonical(getattr(event, field, None)) for field in _HASHED_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def verify_row(event: AuditEvent) -> bool | None:
    """Does this row still hash to what it claims?

    ``True`` intact, ``False`` altered, ``None`` unverifiable — the last for rows
    written before ``record_hash`` existed. Three answers rather than two,
    because reporting a pre-existing row as *altered* would cry wolf and reporting
    it as *intact* would be a claim the data cannot support.
    """

    if not event.record_hash:
        return None
    return event.record_hash == compute_record_hash(event)


@dataclass(frozen=True)
class IntegrityReport:
    """The result of sweeping a set of audit rows for tampering."""

    checked: int
    intact: int
    altered: int
    unverifiable: int
    altered_ids: list[uuid.UUID]

    @property
    def ok(self) -> bool:
        return self.altered == 0


def verify_integrity(
    session: Session,
    *,
    org_id: uuid.UUID | None = None,
    limit: int = 5000,
) -> IntegrityReport:
    """Re-hash recent audit rows and report any that no longer match.

    Bounded by ``limit`` on purpose: this runs from an HTTP request, and an
    unbounded re-hash of every row a mature org has ever produced is a
    self-inflicted denial of service. Newest-first, because a tamperer edits
    what is still being looked at.
    """

    statement = select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)
    if org_id is not None:
        statement = statement.where(AuditEvent.org_id == org_id)

    intact = altered = unverifiable = 0
    altered_ids: list[uuid.UUID] = []
    rows = list(session.scalars(statement))
    for row in rows:
        verdict = verify_row(row)
        if verdict is None:
            unverifiable += 1
        elif verdict:
            intact += 1
        else:
            altered += 1
            altered_ids.append(row.id)

    return IntegrityReport(
        checked=len(rows),
        intact=intact,
        altered=altered,
        unverifiable=unverifiable,
        altered_ids=altered_ids,
    )


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

    ``request_id``, ``ip_hash`` and ``user_agent`` default to the ambient
    request's values (:mod:`app.request_context`) when the caller does not pass
    them, which is how every pre-existing call site gained those fields without
    being rewritten. An explicit argument always wins, so a worker that knows
    better is not overridden by whatever request happens to be on the stack.

    Returns the row, or ``None`` if the write failed. Adds to the session
    without committing: the event belongs in the caller's transaction, so an
    action that rolls back does not leave an audit row claiming it happened.
    """

    try:
        info = current_request_info()
        if info is not None:
            request_id = request_id or info.request_id
            ip_hash = ip_hash or info.ip_hash
            user_agent = user_agent or info.user_agent

        event = AuditEvent(
            id=uuid.uuid4(),
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
        # Hashed before the insert, over the values as constructed — not read
        # back afterwards, which would hash whatever the database returned and
        # so would verify a row against itself rather than against the event.
        event.record_hash = compute_record_hash(event)
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


# ---------------------------------------------------------------------------
# Querying — what the Admin Panel's audit log runs on
#
# There was briefly a second, simpler pair of readers here (`events_for_org`
# and `entity_timeline`). They were removed rather than kept: `search_events`
# below answers both questions, nothing in the application called them, and two
# ways to read the same table is two places for a scoping rule to be applied
# differently. The tests that covered them now exercise the path the product
# actually uses.
# ---------------------------------------------------------------------------

# Sortable columns are an allow-list, not a getattr on user input. An
# attacker-chosen ORDER BY is not injection here (SQLAlchemy would quote it) but
# it does let a caller sort by a column the response never shows, which is a way
# to read one field's ordering out of rows they otherwise only see redacted.
SORTABLE = {
    "occurred_at": AuditEvent.occurred_at,
    "action": AuditEvent.action,
    "actor_label": AuditEvent.actor_label,
    "entity_type": AuditEvent.entity_type,
    "outcome": AuditEvent.outcome,
}
DEFAULT_SORT = "occurred_at"


@dataclass(frozen=True)
class EventQuery:
    """Every way the audit log can be narrowed. All optional, all combinable.

    A dataclass rather than a pile of keyword arguments because the route, the
    service and the tests all need to agree on the shape, and because adding a
    filter should be one field rather than three signatures.
    """

    org_id: uuid.UUID | None = None
    q: str | None = None
    action: str | None = None
    actor_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    outcome: str | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    sort: str = DEFAULT_SORT
    descending: bool = True
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class EventPage:
    """One page of results, plus the total the filters matched."""

    total: int
    events: list[AuditEvent]


def _apply_filters(statement: Select, query: EventQuery) -> Select:
    if query.org_id is not None:
        statement = statement.where(AuditEvent.org_id == query.org_id)
    if query.action:
        # Prefix match, so `member:` finds every membership event without the
        # caller having to know the full taxonomy. `member:update` still matches
        # itself exactly, so the precise query is unaffected.
        statement = statement.where(AuditEvent.action.like(f"{query.action}%"))
    if query.actor_id is not None:
        statement = statement.where(AuditEvent.actor_id == query.actor_id)
    if query.entity_type:
        statement = statement.where(AuditEvent.entity_type == query.entity_type)
    if query.entity_id is not None:
        statement = statement.where(AuditEvent.entity_id == query.entity_id)
    if query.outcome:
        statement = statement.where(AuditEvent.outcome == query.outcome)
    if query.occurred_from is not None:
        statement = statement.where(AuditEvent.occurred_at >= query.occurred_from)
    if query.occurred_to is not None:
        statement = statement.where(AuditEvent.occurred_at <= query.occurred_to)
    if query.q:
        needle = f"%{query.q.strip().lower()}%"
        # Searched across the three human-readable columns only. Deliberately NOT
        # over before/after: those are JSON of arbitrary shape, a LIKE over them
        # is a full scan on every row, and the fields most worth searching are
        # exactly the ones redaction has already replaced.
        statement = statement.where(
            or_(
                func.lower(AuditEvent.action).like(needle),
                func.lower(AuditEvent.actor_label).like(needle),
                func.lower(AuditEvent.entity_type).like(needle),
            )
        )
    return statement


def search_events(session: Session, query: EventQuery) -> EventPage:
    """Filter, search, sort and page the audit trail.

    The total is computed over the same filtered statement rather than the whole
    table, so "showing 1–50 of 3" means what a reader assumes it means.

    The sort always ends with ``id`` as a tiebreaker. Two events written inside
    the same transaction share a timestamp to microsecond precision often enough
    that without it, page 2 can repeat a row from page 1 and skip another — the
    classic unstable-pagination bug, and an especially bad one in a log people
    read to prove a negative.
    """

    base = _apply_filters(select(AuditEvent), query)
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)

    column = SORTABLE.get(query.sort, SORTABLE[DEFAULT_SORT])
    primary = column.desc() if query.descending else column.asc()
    tiebreak = AuditEvent.id.desc() if query.descending else AuditEvent.id.asc()

    rows = list(
        session.scalars(
            base.order_by(primary, tiebreak).limit(max(1, query.limit)).offset(max(0, query.offset))
        )
    )
    return EventPage(total=total, events=rows)


def distinct_actions(session: Session, *, org_id: uuid.UUID | None, limit: int = 200) -> list[str]:
    """The action strings this org has actually produced.

    The filter dropdown is built from these rather than from a constant, because
    the taxonomy is deliberately open (``resource:action`` strings, no enum) and
    a hardcoded list would offer filters that match nothing while hiding the ones
    that do.
    """

    statement = select(AuditEvent.action).distinct().order_by(AuditEvent.action).limit(limit)
    if org_id is not None:
        statement = statement.where(AuditEvent.org_id == org_id)
    result: Sequence[str] = session.scalars(statement).all()
    return [action for action in result if action]
