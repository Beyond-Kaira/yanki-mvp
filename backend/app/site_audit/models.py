"""Internal crawl and analysis values; persistence models live in app.db.models."""

from dataclasses import dataclass, field
from typing import Any, Literal

AuditProfileId = Literal["site_audit_mobile", "site_audit_desktop"]
IssueSeverity = Literal["error", "warning", "notice"]


@dataclass(frozen=True)
class CrawlerProfile:
    profile_id: AuditProfileId
    label: str
    browser_user_agent: str
    robots_user_agent: str
    viewport_width: int
    viewport_height: int
    is_mobile: bool
    has_touch: bool


@dataclass(frozen=True)
class CrawlConfig:
    page_limit: int
    profile: CrawlerProfile
    js_rendering: bool
    render_wait_ms: int
    page_timeout_ms: int
    crawl_delay_seconds: float
    max_robots_bytes: int
    sitemap_url_limit: int
    max_sitemap_bytes: int
    max_html_chars: int
    max_queue_urls: int
    max_query_variants_per_path: int = 3


@dataclass
class CrawledPage:
    requested_url: str
    final_url: str
    status_code: int
    raw_html: str = ""
    rendered_html: str | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    blocked_by_robots: bool = False

    @property
    def analysis_html(self) -> str:
        return self.rendered_html if self.rendered_html is not None else self.raw_html


@dataclass(frozen=True)
class ParsedPage:
    title: str
    h1_count: int
    meta_description: str | None
    html_lang: str | None
    images_missing_alt: int
    empty_anchors: int
    hreflangs: list[dict[str, str | None]]
    raw_schemas: list[str]


@dataclass(frozen=True)
class AuditIssue:
    code: str
    severity: IssueSeverity
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class AnalyzedPage:
    requested_url: str
    final_url: str
    status_code: int
    title: str
    h1_count: int
    meta_description: str | None
    html_lang: str | None
    issues: list[dict[str, Any]]
    schemas: list[dict[str, Any]]
