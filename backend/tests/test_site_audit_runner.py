"""Durable Site Audit runner behavior without launching a real browser."""

from sqlalchemy import select

from app.db.models import Analysis, SeoProject, SiteAudit, SiteAuditPage, User
from app.site_audit.models import CrawledPage
from app.site_audit.runner import run_site_audit


def test_runner_persists_pages_and_leaves_geo_pipeline_untouched(
    db_session, make_analysis, settings, monkeypatch
):
    geo = make_analysis(url="https://geo.example", status="queued")
    user = User(email="audit-owner@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    project = SeoProject(
        user_id=user.id,
        name="Example",
        domain="https://example.com/",
        domain_key="example.com",
    )
    audit = SiteAudit(project=project, page_limit=5, status="running", attempts=1)
    db_session.add_all([user, project, audit])
    db_session.commit()

    def fake_crawl(seed_url, config, *, on_page, on_discovery, on_heartbeat):
        assert seed_url == "https://example.com/"
        assert config.page_limit == 5
        on_discovery(2)
        on_page(
            CrawledPage(
                requested_url=seed_url,
                final_url=seed_url,
                status_code=200,
                raw_html=(
                    '<html lang="en"><head><title>Example</title>'
                    '<meta name="description" content="Description"></head>'
                    "<body><h1>Welcome</h1></body></html>"
                ),
            ),
            2,
        )
        on_page(
            CrawledPage(
                requested_url="https://example.com/private",
                final_url="https://example.com/private",
                status_code=0,
                blocked_by_robots=True,
            ),
            2,
        )
        return 2

    monkeypatch.setattr("app.site_audit.runner.crawl_site", fake_crawl)

    run_site_audit(db_session, audit.id, settings)
    db_session.expire_all()

    result = db_session.get(SiteAudit, audit.id)
    assert result is not None
    assert result.status == "done"
    assert result.progress == 100
    assert result.health_score == 100
    assert result.pages_discovered == 2
    assert result.pages_crawled == 2
    assert result.total_notices == 1
    assert result.completed_at is not None

    pages = list(
        db_session.scalars(
            select(SiteAuditPage).where(SiteAuditPage.audit_id == audit.id)
        )
    )
    assert len(pages) == 2
    assert pages[1].issues[0]["code"] == "blocked_by_robots"

    untouched_geo = db_session.get(Analysis, geo.id)
    assert untouched_geo is not None
    assert untouched_geo.status == "queued"
    assert untouched_geo.attempts == 0


def test_runner_keeps_health_score_null_when_every_page_is_unscoreable(
    db_session, settings, monkeypatch
):
    user = User(email="robots-only@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    project = SeoProject(
        user_id=user.id,
        name="Robots only",
        domain="https://example.com/",
        domain_key="example.com",
    )
    audit = SiteAudit(project=project, page_limit=1, status="running", attempts=1)
    db_session.add_all([project, audit])
    db_session.commit()

    def fake_crawl(seed_url, config, *, on_page, on_discovery, on_heartbeat):
        on_discovery(1)
        on_page(
            CrawledPage(
                requested_url=seed_url,
                final_url=seed_url,
                status_code=0,
                blocked_by_robots=True,
            ),
            1,
        )
        return 1

    monkeypatch.setattr("app.site_audit.runner.crawl_site", fake_crawl)

    run_site_audit(db_session, audit.id, settings)
    db_session.expire_all()

    result = db_session.get(SiteAudit, audit.id)
    assert result is not None
    assert result.status == "done"
    assert result.health_score is None


def test_long_sitemap_discovery_refreshes_audit_heartbeat(
    db_session, settings, monkeypatch
):
    import app.site_audit.runner as runner_module

    user = User(email="heartbeat@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    project = SeoProject(
        user_id=user.id,
        name="Heartbeat",
        domain="https://example.com/",
        domain_key="example.com",
    )
    audit = SiteAudit(project=project, page_limit=1, status="running", attempts=1)
    db_session.add_all([project, audit])
    db_session.commit()

    clock = {"seconds": 0.0}
    monkeypatch.setattr(
        runner_module.time,
        "monotonic",
        lambda: clock["seconds"],
    )
    observations: dict[str, bool] = {}

    def fake_crawl(seed_url, config, *, on_page, on_discovery, on_heartbeat):
        initial_claim = audit.claimed_at
        clock["seconds"] = 10
        on_heartbeat()
        observations["throttled"] = audit.claimed_at == initial_claim

        clock["seconds"] = 31
        on_heartbeat()
        observations["refreshed"] = audit.claimed_at != initial_claim
        return 0

    monkeypatch.setattr(runner_module, "crawl_site", fake_crawl)

    run_site_audit(db_session, audit.id, settings)

    assert observations == {"throttled": True, "refreshed": True}
