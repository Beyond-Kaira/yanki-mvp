"""Run one Site Audit and durably persist every completed page."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import SeoProject, SiteAudit, SiteAuditPage
from app.site_audit.analyzer import analyze_page
from app.site_audit.crawler import crawl_site
from app.site_audit.models import AnalyzedPage, CrawlConfig, CrawledPage
from app.site_audit.profiles import get_profile
from app.site_audit.scoring import audit_health_score, page_health_score


def _severity_counts(issues: list[dict[str, Any]]) -> tuple[int, int, int]:
    return (
        sum(issue.get("severity") == "error" for issue in issues),
        sum(issue.get("severity") == "warning" for issue in issues),
        sum(issue.get("severity") == "notice" for issue in issues),
    )


def _page_row(audit_id: uuid.UUID, page: AnalyzedPage) -> SiteAuditPage:
    return SiteAuditPage(
        audit_id=audit_id,
        requested_url=page.requested_url,
        final_url=page.final_url,
        status_code=page.status_code,
        title=page.title,
        h1_count=page.h1_count,
        meta_description=page.meta_description,
        html_lang=page.html_lang,
        issues=page.issues,
        schemas=page.schemas,
    )


def run_site_audit(
    session: Session,
    audit_id: uuid.UUID,
    settings: Settings,
) -> None:
    audit = session.get(SiteAudit, audit_id)
    if audit is None:
        raise RuntimeError("Site Audit job no longer exists")
    project = session.get(SeoProject, audit.project_id)
    if project is None:
        raise RuntimeError("SEO project no longer exists")

    # A stale job is restarted from a clean page set. This avoids mixing a
    # partial browser snapshot from the crashed attempt with the new crawl.
    session.execute(delete(SiteAuditPage).where(SiteAuditPage.audit_id == audit_id))
    audit.status = "running"
    audit.progress = 2
    audit.current_step = "discovery"
    audit.started_at = audit.started_at or datetime.now(UTC)
    audit.claimed_at = datetime.now(UTC)
    audit.completed_at = None
    audit.pages_discovered = 0
    audit.pages_crawled = 0
    audit.total_errors = 0
    audit.total_warnings = 0
    audit.total_notices = 0
    audit.health_score = None
    session.commit()

    heartbeat_interval = max(
        0.1,
        min(30.0, settings.site_audit_stale_claim_seconds / 3),
    )
    last_heartbeat = time.monotonic()

    config = CrawlConfig(
        page_limit=audit.page_limit,
        profile=get_profile(audit.profile_id),
        js_rendering=audit.js_rendering,
        render_wait_ms=settings.site_audit_render_wait_ms,
        page_timeout_ms=settings.site_audit_page_timeout_ms,
        crawl_delay_seconds=settings.site_audit_crawl_delay_seconds,
        max_robots_bytes=settings.site_audit_max_robots_bytes,
        sitemap_url_limit=settings.site_audit_sitemap_url_limit,
        max_sitemap_bytes=settings.site_audit_max_sitemap_bytes,
        max_html_chars=settings.site_audit_max_html_chars,
        max_queue_urls=settings.site_audit_max_queue_urls,
        failure_backoff_max_seconds=settings.site_audit_failure_backoff_max_seconds,
        max_consecutive_failures=settings.site_audit_max_consecutive_failures,
    )
    persisted_urls: set[str] = set()
    scores: list[int | None] = []

    def on_discovery(discovered: int) -> None:
        nonlocal last_heartbeat
        audit.pages_discovered = discovered
        audit.claimed_at = datetime.now(UTC)
        if audit.pages_crawled == 0:
            audit.progress = 8
            audit.current_step = "discovery"
        session.commit()
        last_heartbeat = time.monotonic()

    def on_heartbeat() -> None:
        nonlocal last_heartbeat
        now = time.monotonic()
        if now - last_heartbeat < heartbeat_interval:
            return
        audit.claimed_at = datetime.now(UTC)
        session.commit()
        last_heartbeat = now

    def on_page(crawled: CrawledPage, discovered: int) -> None:
        analyzed = analyze_page(crawled)
        if analyzed.final_url in persisted_urls:
            audit.pages_discovered = discovered
            audit.claimed_at = datetime.now(UTC)
            session.commit()
            return

        persisted_urls.add(analyzed.final_url)
        session.add(_page_row(audit_id, analyzed))
        errors, warnings, notices = _severity_counts(analyzed.issues)
        audit.pages_discovered = discovered
        audit.pages_crawled += 1
        audit.total_errors += errors
        audit.total_warnings += warnings
        audit.total_notices += notices
        audit.current_step = "crawl"
        audit.progress = min(85, 10 + round(75 * audit.pages_crawled / audit.page_limit))
        audit.claimed_at = datetime.now(UTC)
        scores.append(page_health_score(analyzed.status_code, analyzed.issues))
        session.commit()

    crawl_site(
        project.domain,
        config,
        on_page=on_page,
        on_discovery=on_discovery,
        on_heartbeat=on_heartbeat,
    )

    audit.current_step = "finalize"
    audit.progress = 95
    audit.claimed_at = datetime.now(UTC)
    session.commit()

    audit.health_score = audit_health_score(scores)
    audit.status = "done"
    audit.progress = 100
    audit.current_step = None
    audit.completed_at = datetime.now(UTC)
    session.commit()
