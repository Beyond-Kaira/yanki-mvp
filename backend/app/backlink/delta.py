"""The import and delta engine — where an observation becomes a claim.

This is the module the whole milestone's credibility rests on. A backlink tool
that announces "you lost 4,000 links" on a day nothing happened has destroyed
the thing it was selling, and every plausible implementation of a link diff does
exactly that at least once. Four specific ways, all guarded here:

1. **A truncated page looks like mass deletion.** A vendor returning 200 rows
   instead of 4,000 because a cursor expired is not evidence that 3,800 links
   died. Guarded by :func:`is_measurable`: an import that is not whole may ADD
   what it saw, and may never SUBTRACT.

2. **A per-plan row cap looks like mass creation.** If "new" meant "absent from
   our stored rows", then raising a customer's cap — the happiest day of their
   month — would mint tens of thousands of fake birth events. Guarded by
   classifying birth from the **vendor's** ``first_seen``, which is a fact about
   the web rather than about our storage.

3. **Cosmetic URL churn looks like churn.** A vendor tidying ``?utm_source`` out
   of its URLs would retire every link and create an identical new one. Guarded
   by canonical keys (``normalize.url_key``).

4. **A flapping index looks like constant turnover.** A link that disappears for
   one cycle and returns is not born twice. Guarded by ``regained``, and by
   requiring N consecutive misses before absence is even provisional.

The state machine, therefore: ``active`` → (missed in a measurable import) →
``missing_pending`` → (missed again) → ``lost``. A link seen again at any point
returns to ``active`` and emits ``regained``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backlink.base import BacklinkPage, BacklinkRow, BacklinkSource, BacklinkSourceUnavailable
from app.backlink.normalize import classify_anchor, domain_key, subnet_24, url_key
from app.db.models import Backlink, BacklinkImport, LinkEvent, ReferringDomainRollup

# How many consecutive measurable misses before a link is called lost. Two, not
# one: a single-cycle disappearance is the most common form of index flapping,
# and calling it a loss is the error customers notice.
MISSES_BEFORE_LOST = 2

# An import whose row count collapses to under this fraction of the previous
# one is treated as untrustworthy even if the vendor called it "complete" — the
# vendor's own status is a claim, and a 90% drop is better explained by a broken
# pull than by a catastrophe. Compared against the PRIOR IMPORT's ingested rows,
# never against the vendor's grand total: comparing retained rows to a grand
# total would quarantine every capped profile forever.
SHRINK_FLOOR = 0.5


@dataclass(frozen=True)
class ImportOutcome:
    """What one refresh concluded. Returned for the caller to log or assert on."""

    import_id: uuid.UUID
    measurable: bool
    coverage_status: str
    rows_ingested: int
    new_links: int
    lost_links: int
    regained_links: int
    changed_links: int
    cost_usd: Decimal


def is_measurable(page: BacklinkPage, *, previous_rows: int | None) -> bool:
    """May this import support an absence claim?

    Two independent gates. The page must call itself complete, and it must not
    have collapsed relative to the last import. Either alone is insufficient:
    vendors report "complete" for pages that are not, and a genuinely small
    profile is not suspicious just because it is small.
    """

    if not page.measurable:
        return False
    if previous_rows is None or previous_rows == 0:
        return True
    return len(page.rows) >= previous_rows * SHRINK_FLOOR


def _row_identity(row: BacklinkRow) -> tuple[str, str]:
    return url_key(row.source_url), url_key(row.target_url)


def run_import(
    session: Session,
    *,
    source: BacklinkSource,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    subject_domain: str,
    brand: str = "",
    trigger: str = "manual",
    now: datetime | None = None,
) -> ImportOutcome:
    """Fetch one profile, diff it against what we believed, record the truth.

    ``now`` is injectable because every assertion in the delta tests is about
    ordering across cycles, and a test that depends on the wall clock is a test
    that fails at midnight.
    """

    moment = now or datetime.now(UTC)
    subject = domain_key(subject_domain) or subject_domain

    record = BacklinkImport(
        org_id=org_id,
        project_id=project_id,
        subject_domain=subject,
        subject_kind="own",
        vendor=getattr(source, "name", "unknown"),
        trigger=trigger,
        status="running",
        claimed_at=moment,
    )
    session.add(record)
    session.flush()

    try:
        page = source.fetch_backlinks(subject)
    except BacklinkSourceUnavailable as exc:
        # The refresh degrades; it never fails the job and never mints a loss.
        record.status = "failed"
        record.coverage_status = "failed"
        record.measurable = False
        record.error = str(exc)[:500]
        record.completed_at = moment
        session.flush()
        return ImportOutcome(
            import_id=record.id,
            measurable=False,
            coverage_status="failed",
            rows_ingested=0,
            new_links=0,
            lost_links=0,
            regained_links=0,
            changed_links=0,
            cost_usd=Decimal("0"),
        )

    previous = session.scalar(
        select(BacklinkImport)
        .where(
            BacklinkImport.project_id == project_id,
            BacklinkImport.subject_domain == subject,
            BacklinkImport.id != record.id,
            BacklinkImport.status == "done",
        )
        .order_by(BacklinkImport.created_at.desc())
        .limit(1)
    )
    measurable = is_measurable(page, previous_rows=previous.rows_ingested if previous else None)

    existing = {
        (b.source_url_key, b.target_url_key): b
        for b in session.scalars(
            select(Backlink).where(
                Backlink.project_id == project_id,
                Backlink.vendor == record.vendor,
                Backlink.subject_domain == subject,
            )
        )
    }

    seen: set[tuple[str, str]] = set()
    counts = {"new": 0, "regained": 0, "changed": 0, "lost": 0}

    for row in page.rows:
        identity = _row_identity(row)
        seen.add(identity)
        current = existing.get(identity)
        first_seen = row.vendor_first_seen or moment
        last_seen = row.vendor_last_seen or moment
        anchor_class = classify_anchor(row.anchor, brand=brand, target_domain=row.target_url)

        if current is None:
            link = Backlink(
                org_id=org_id,
                project_id=project_id,
                subject_domain=subject,
                vendor=record.vendor,
                source_url=row.source_url,
                source_url_key=identity[0],
                source_domain=domain_key(row.source_domain) or row.source_domain,
                target_url=row.target_url,
                target_url_key=identity[1],
                anchor=row.anchor,
                anchor_class=anchor_class,
                is_follow="nofollow" not in row.attrs,
                is_image_link=row.is_image_link,
                tld=row.source_tld or None,
                attrs=list(row.attrs),
                vendor_metrics=dict(row.raw),
                status="active",
                first_seen_at=first_seen,
                last_seen_at=last_seen,
                last_import_id=record.id,
                source_domain_authority=row.source_domain_authority,
                source_page_authority=row.source_page_authority,
                vendor_spam_score=row.vendor_spam_score,
            )
            session.add(link)
            session.flush()
            counts["new"] += 1
            _emit(
                session,
                record,
                link,
                kind="new",
                occurred_at=moment,
                authority=row.source_domain_authority,
            )
            continue

        was_absent = current.status in {"missing_pending", "lost", "lost_unverified"}
        if was_absent:
            counts["regained"] += 1
            _emit(
                session,
                record,
                current,
                kind="regained",
                occurred_at=moment,
                authority=row.source_domain_authority,
                reason=current.lost_reason,
            )
        elif current.anchor != row.anchor:
            counts["changed"] += 1
            _emit(
                session,
                record,
                current,
                kind="changed",
                occurred_at=moment,
                authority=row.source_domain_authority,
                detail={"field": "anchor", "from": current.anchor, "to": row.anchor},
            )

        current.status = "active"
        current.consecutive_misses = 0
        current.lost_at = None
        current.lost_reason = None
        current.anchor = row.anchor
        current.anchor_class = anchor_class
        current.is_follow = "nofollow" not in row.attrs
        current.last_seen_at = last_seen
        current.last_import_id = record.id
        current.source_domain_authority = row.source_domain_authority
        current.vendor_spam_score = row.vendor_spam_score

    # Absences. Only a measurable import gets to look at these at all.
    if measurable:
        for identity, link in existing.items():
            if identity in seen or link.status in {"lost", "lost_unverified"}:
                continue
            link.consecutive_misses += 1
            if link.consecutive_misses >= MISSES_BEFORE_LOST:
                link.status = "lost"
                link.lost_at = moment
                link.lost_reason = "absent_from_index"
                counts["lost"] += 1
                _emit(
                    session,
                    record,
                    link,
                    kind="lost",
                    occurred_at=moment,
                    authority=link.source_domain_authority,
                    reason="absent_from_index",
                )
            else:
                link.status = "missing_pending"

    record.status = "done" if page.coverage_status == "complete" else "partial"
    record.coverage_status = page.coverage_status
    record.measurable = measurable
    record.rows_ingested = len(page.rows)
    record.reported_total_backlinks = page.reported_total_backlinks
    record.reported_total_referring_domains = page.reported_total_referring_domains
    record.cost_usd = page.cost
    record.snapshot_at = page.fetched_at or moment
    record.new_in_period = counts["new"]
    record.lost_in_period = counts["lost"]
    record.completed_at = moment
    record.provenance = {
        "vendor": record.vendor,
        "fetched_at": (page.fetched_at or moment).isoformat(),
        "coverage_note": (
            "complete pull"
            if measurable
            else "incomplete or shrunken pull — recorded, but no losses claimed"
        ),
    }
    session.flush()

    rebuild_rollups(
        session,
        org_id=org_id,
        project_id=project_id,
        subject_domain=subject,
        subject_kind="own",
        import_id=record.id,
    )

    return ImportOutcome(
        import_id=record.id,
        measurable=measurable,
        coverage_status=page.coverage_status,
        rows_ingested=len(page.rows),
        new_links=counts["new"],
        lost_links=counts["lost"],
        regained_links=counts["regained"],
        changed_links=counts["changed"],
        cost_usd=page.cost,
    )


def _emit(
    session: Session,
    record: BacklinkImport,
    link: Backlink,
    *,
    kind: str,
    occurred_at: datetime,
    authority: float | None = None,
    reason: str | None = None,
    detail: dict | None = None,
) -> None:
    """Append one fact to the event log.

    Denormalized on purpose — an event must stay readable after the link row it
    describes is pruned by a plan cap. History that depends on the inventory is
    history that a billing change can erase.
    """

    session.add(
        LinkEvent(
            org_id=record.org_id,
            project_id=record.project_id,
            backlink_id=link.id,
            import_id=record.id,
            subject_domain=record.subject_domain,
            vendor=record.vendor,
            source_url_key=link.source_url_key,
            target_url_key=link.target_url_key,
            source_domain=link.source_domain,
            source_url=link.source_url,
            target_url=link.target_url,
            kind=kind,
            reason=reason,
            detected_by="vendor",
            verified=False,
            detail=detail,
            authority_at_event=authority,
            occurred_at=occurred_at,
        )
    )


def rebuild_rollups(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    subject_domain: str,
    subject_kind: str,
    import_id: uuid.UUID | None = None,
    rows: list[BacklinkRow] | None = None,
) -> int:
    """Recompute per-referring-domain state for one subject.

    For the project's own domain this rolls up the stored ``Backlink`` rows. For
    a competitor it rolls up the fetched rows directly, because competitor links
    are never stored individually — the gap analysis needs their *domains*, and
    storing their links would multiply row count by the competitor count for no
    question anyone asks.
    """

    grouped: dict[str, dict] = {}

    if rows is not None:
        for row in rows:
            key = domain_key(row.source_domain) or row.source_domain
            bucket = grouped.setdefault(
                key,
                {
                    "links": 0,
                    "follow": 0,
                    "first": None,
                    "last": None,
                    "authority": row.source_domain_authority,
                    "subnet": subnet_24(row.source_ip),
                    "spam": row.vendor_spam_score,
                    "tld": row.source_tld,
                },
            )
            bucket["links"] += 1
            bucket["follow"] += 0 if "nofollow" in row.attrs else 1
            for field, value in (("first", row.vendor_first_seen), ("last", row.vendor_last_seen)):
                if value is None:
                    continue
                if bucket[field] is None:
                    bucket[field] = value
                elif field == "first":
                    bucket[field] = min(bucket[field], value)
                else:
                    bucket[field] = max(bucket[field], value)
    else:
        stored = session.scalars(
            select(Backlink).where(
                Backlink.project_id == project_id,
                Backlink.subject_domain == subject_domain,
                Backlink.status == "active",
            )
        )
        for link in stored:
            bucket = grouped.setdefault(
                link.source_domain,
                {
                    "links": 0,
                    "follow": 0,
                    "first": None,
                    "last": None,
                    "authority": link.source_domain_authority,
                    "subnet": None,
                    "spam": link.vendor_spam_score,
                    "tld": link.tld,
                },
            )
            bucket["links"] += 1
            bucket["follow"] += 1 if link.is_follow else 0
            bucket["first"] = (
                link.first_seen_at
                if bucket["first"] is None
                else min(bucket["first"], link.first_seen_at)
            )
            bucket["last"] = (
                link.last_seen_at
                if bucket["last"] is None
                else max(bucket["last"], link.last_seen_at)
            )

    existing = {
        r.referring_domain: r
        for r in session.scalars(
            select(ReferringDomainRollup).where(
                ReferringDomainRollup.project_id == project_id,
                ReferringDomainRollup.subject_domain == subject_domain,
            )
        )
    }

    for referring_domain, bucket in grouped.items():
        rollup = existing.get(referring_domain)
        if rollup is None:
            rollup = ReferringDomainRollup(
                org_id=org_id,
                project_id=project_id,
                subject_domain=subject_domain,
                subject_kind=subject_kind,
                referring_domain=referring_domain,
            )
            session.add(rollup)
        rollup.links_count = bucket["links"]
        rollup.follow_links = bucket["follow"]
        rollup.first_linked_at = bucket["first"]
        rollup.last_linked_at = bucket["last"]
        rollup.domain_authority = bucket["authority"]
        rollup.source_subnet = bucket["subnet"] or rollup.source_subnet
        rollup.last_import_id = import_id

    # A domain that no longer refers anything drops to zero rather than
    # vanishing: the row carries first_linked_at, which is history.
    for referring_domain, rollup in existing.items():
        if referring_domain not in grouped:
            rollup.links_count = 0
            rollup.follow_links = 0

    session.flush()
    return len(grouped)
