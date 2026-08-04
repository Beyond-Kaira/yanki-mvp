"""Stable-code technical SEO rules.

Messages are presentation copy; ``code`` is the finding identity used for
aggregation across pages.
"""

from collections import Counter

from app.site_audit.models import AuditIssue, CrawledPage, ParsedPage


def evaluate_page(crawled: CrawledPage, parsed: ParsedPage) -> list[AuditIssue]:
    issues: list[AuditIssue] = []

    if crawled.status_code < 200 or crawled.status_code >= 400:
        issues.append(
            AuditIssue(
                code="http_status_error",
                severity="error",
                message=f"Server returned HTTP status {crawled.status_code}.",
                details={"status_code": crawled.status_code},
            )
        )
    elif 300 <= crawled.status_code < 400:
        issues.append(
            AuditIssue(
                code="http_redirect",
                severity="warning",
                message=f"Page returned redirect status {crawled.status_code}.",
                details={"status_code": crawled.status_code},
            )
        )

    if crawled.requested_url != crawled.final_url:
        issues.append(
            AuditIssue(
                code="url_redirected",
                severity="notice",
                message="Requested URL redirected to another in-scope URL.",
                details={
                    "requested_url": crawled.requested_url,
                    "final_url": crawled.final_url,
                },
            )
        )

    if not parsed.title:
        issues.append(
            AuditIssue(
                code="missing_title",
                severity="error",
                message="Page does not have a title element.",
            )
        )
    elif len(parsed.title) > 60:
        issues.append(
            AuditIssue(
                code="title_too_long",
                severity="warning",
                message="Title contains more than 60 characters.",
                details={"character_count": len(parsed.title), "recommended_max": 60},
            )
        )

    if parsed.h1_count == 0:
        issues.append(
            AuditIssue(
                code="missing_h1",
                severity="error",
                message="Page does not have an H1 heading.",
            )
        )
    elif parsed.h1_count > 1:
        issues.append(
            AuditIssue(
                code="multiple_h1",
                severity="warning",
                message="Page has more than one H1 heading.",
                details={"count": parsed.h1_count},
            )
        )

    if not parsed.meta_description:
        issues.append(
            AuditIssue(
                code="missing_meta_description",
                severity="warning",
                message="Page does not have a meta description.",
            )
        )
    if not parsed.html_lang:
        issues.append(
            AuditIssue(
                code="missing_html_lang",
                severity="warning",
                message="HTML element does not declare a language.",
            )
        )
    if parsed.images_missing_alt:
        issues.append(
            AuditIssue(
                code="missing_image_alt",
                severity="warning",
                message="One or more images have no alternative text.",
                details={"count": parsed.images_missing_alt},
            )
        )
    if parsed.empty_anchors:
        issues.append(
            AuditIssue(
                code="empty_anchor_text",
                severity="notice",
                message="One or more links have no accessible anchor text.",
                details={"count": parsed.empty_anchors},
            )
        )

    hreflang_counts = Counter(
        str(entry["lang"]) for entry in parsed.hreflangs if entry.get("lang")
    )
    duplicates = sorted(lang for lang, count in hreflang_counts.items() if count > 1)
    if duplicates:
        issues.append(
            AuditIssue(
                code="duplicate_hreflang",
                severity="error",
                message="Page declares duplicate hreflang values.",
                details={"languages": duplicates},
            )
        )

    return issues


def crawl_failure_issue(message: str) -> AuditIssue:
    return AuditIssue(
        code="crawl_failed",
        severity="error",
        message="Page could not be crawled.",
        details={"reason": message},
    )


def robots_blocked_issue() -> AuditIssue:
    return AuditIssue(
        code="blocked_by_robots",
        severity="notice",
        message="Page is blocked by robots.txt for the Site Audit crawler.",
    )
