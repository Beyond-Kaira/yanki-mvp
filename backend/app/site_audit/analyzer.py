"""Turn one browser crawl snapshot into the persisted page result shape."""

from app.site_audit.models import AnalyzedPage, CrawledPage
from app.site_audit.parser import parse_page
from app.site_audit.rules import crawl_failure_issue, evaluate_page, robots_blocked_issue
from app.site_audit.schema_validator import validate_schemas


def analyze_page(crawled: CrawledPage) -> AnalyzedPage:
    if crawled.blocked_by_robots:
        return AnalyzedPage(
            requested_url=crawled.requested_url,
            final_url=crawled.final_url or crawled.requested_url,
            status_code=0,
            title="",
            h1_count=0,
            meta_description=None,
            html_lang=None,
            issues=[robots_blocked_issue().as_dict()],
            schemas=[],
        )
    if crawled.error:
        return AnalyzedPage(
            requested_url=crawled.requested_url,
            final_url=crawled.final_url or crawled.requested_url,
            status_code=crawled.status_code,
            title="",
            h1_count=0,
            meta_description=None,
            html_lang=None,
            issues=[crawl_failure_issue(crawled.error).as_dict()],
            schemas=[],
        )

    parsed = parse_page(crawled.analysis_html, crawled.final_url)
    return AnalyzedPage(
        requested_url=crawled.requested_url,
        final_url=crawled.final_url,
        status_code=crawled.status_code,
        title=parsed.title,
        h1_count=parsed.h1_count,
        meta_description=parsed.meta_description,
        html_lang=parsed.html_lang,
        issues=[issue.as_dict() for issue in evaluate_page(crawled, parsed)],
        schemas=validate_schemas(parsed.raw_schemas),
    )
