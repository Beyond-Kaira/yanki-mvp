"""Independent Site Audit queue ordering, staleness, and poison-job tests."""

from datetime import UTC, datetime, timedelta

from app.db.models import SeoProject, SiteAudit, User
from app.site_audit.queue import claim_next_site_audit


def _make_audit(db_session, *, created_offset: int = 0, **kwargs) -> SiteAudit:
    user = User(
        email=f"user-{created_offset}-{len(db_session.new)}@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.flush()
    project = SeoProject(
        user_id=user.id,
        name="Example",
        domain=f"https://example-{created_offset}.com/",
        domain_key=f"example-{created_offset}.com",
    )
    audit = SiteAudit(
        project=project,
        created_at=datetime.now(UTC) + timedelta(seconds=created_offset),
        **kwargs,
    )
    db_session.add(audit)
    db_session.commit()
    return audit


def test_site_audit_queue_claims_oldest_without_claiming_geo(
    db_session, make_analysis, settings
):
    geo = make_analysis(url="https://geo.example", status="queued")
    older = _make_audit(db_session, created_offset=-20)
    _make_audit(db_session, created_offset=-10)

    claimed = claim_next_site_audit(db_session, settings)

    assert claimed is not None
    assert claimed.id == older.id
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert geo.status == "queued"
    assert geo.attempts == 0


def test_site_audit_queue_reclaims_stale_and_fails_after_retry_cap(
    db_session, settings
):
    stale = _make_audit(
        db_session,
        created_offset=-20,
        status="running",
        attempts=3,
        claimed_at=datetime.now(UTC)
        - timedelta(seconds=settings.site_audit_stale_claim_seconds + 10),
    )

    assert claim_next_site_audit(db_session, settings) is None
    assert stale.status == "failed"
    assert stale.error == "max retries exceeded"
    assert stale.completed_at is not None


def test_site_audit_queue_does_not_reclaim_fresh_job(db_session, settings):
    _make_audit(
        db_session,
        status="running",
        claimed_at=datetime.now(UTC),
    )

    assert claim_next_site_audit(db_session, settings) is None
