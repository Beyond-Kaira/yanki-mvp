"""Dedicated worker failure envelope and GEO isolation."""

from app.db.models import Analysis, SeoProject, SiteAudit, User


def test_site_audit_worker_marks_failure_without_claiming_geo(
    session_factory, settings, monkeypatch
):
    import app.site_audit.worker as worker

    seed = session_factory()
    user = User(email="worker-owner@example.com", password_hash="x")
    seed.add(user)
    seed.flush()
    project = SeoProject(
        user_id=user.id,
        name="Example",
        domain="https://example.com/",
        domain_key="example.com",
    )
    audit = SiteAudit(project=project, status="queued")
    geo = Analysis(url="https://geo.example", status="queued")
    seed.add_all([project, audit, geo])
    seed.commit()
    audit_id = audit.id
    geo_id = geo.id
    seed.close()

    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    def fail_run(*args, **kwargs):
        raise RuntimeError("browser crashed")

    monkeypatch.setattr(worker, "run_site_audit", fail_run)

    assert worker.run_once(settings) is True

    check = session_factory()
    try:
        failed = check.get(SiteAudit, audit_id)
        untouched_geo = check.get(Analysis, geo_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.error == "browser crashed"
        assert failed.completed_at is not None
        assert untouched_geo is not None
        assert untouched_geo.status == "queued"
        assert untouched_geo.attempts == 0
    finally:
        check.close()
