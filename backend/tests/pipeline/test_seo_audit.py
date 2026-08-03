"""The SEO / AI-readiness audit: checks, the score, and the grade cap.

The assertions worth reading twice are the ones about what the score is allowed
to hide. A weighted average over fifteen checks can bury the two that decide
whether a company exists to an answer engine at all, and burying them is the one
outcome this feature must not produce.
"""

from __future__ import annotations

import pytest

from app.pipeline import seo_audit
from app.pipeline.discovery import CrawlResult, PageAudit
from app.pipeline.robots import AI_CRAWLERS, CrawlerAccess, RobotsReport
from app.pipeline.seo_audit import (
    CRITICAL,
    FAIL,
    IMPORTANT,
    MINOR,
    NOT_APPLICABLE,
    NOT_MEASURED,
    PASS,
    WARN,
    CheckResult,
    audit,
    audit_grade,
    audit_score,
)


def page(**overrides) -> PageAudit:
    base = dict(
        url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        is_home=True,
        title="Acme Robotics — warehouse automation",
        meta_description="We build warehouse robots.",
        meta_robots="",
        x_robots_tag="",
        canonical="https://example.com/",
        lang="en",
        h1_count=1,
        jsonld_types=("Organization",),
        jsonld_same_as=("https://www.linkedin.com/company/acme",),
        og_keys=("og:title", "og:description"),
        image_count=10,
        images_missing_alt=0,
        server_text_chars=5000,
    )
    base.update(overrides)
    return PageAudit(**base)


def crawl(*pages) -> CrawlResult:
    return CrawlResult(text="x", pages=pages or (page(),))


def robots_allowing_all() -> RobotsReport:
    return RobotsReport(
        measured=True,
        sitemaps=("https://example.com/sitemap.xml",),
        crawlers=tuple(
            CrawlerAccess(c.token, c.product, c.role, True, c.honors_robots) for c in AI_CRAWLERS
        ),
    )


def robots_blocking(*tokens) -> RobotsReport:
    return RobotsReport(
        measured=True,
        sitemaps=("https://example.com/sitemap.xml",),
        crawlers=tuple(
            CrawlerAccess(c.token, c.product, c.role, c.token not in tokens, c.honors_robots)
            for c in AI_CRAWLERS
        ),
    )


def status_of(outcome, check_id: str) -> str:
    return next(c.status for c in outcome.checks if c.check_id == check_id)


# --------------------------------------------------------------------------
# the score
# --------------------------------------------------------------------------


def test_score_is_a_weighted_pass_ratio():
    checks = [
        CheckResult("a", "", CRITICAL, PASS),  # 5 of 5
        CheckResult("b", "", MINOR, FAIL),  # 0 of 1
    ]
    assert audit_score(checks) == pytest.approx(100 * 5 / 6, abs=0.1)


def test_a_warning_is_worth_half():
    assert audit_score([CheckResult("a", "", MINOR, WARN)]) == 50.0


def test_unevaluable_checks_are_in_neither_side_of_the_ratio():
    """The ADR-28 discipline, one layer down.

    A check we could not read must not count as a pass (inflating the score) or
    as a failure (fabricating a problem). It leaves the sum entirely.
    """
    both = [
        CheckResult("a", "", CRITICAL, PASS),
        CheckResult("b", "", CRITICAL, NOT_MEASURED),
        CheckResult("c", "", CRITICAL, NOT_APPLICABLE),
    ]
    assert audit_score(both) == 100.0


def test_score_is_none_when_nothing_could_be_evaluated():
    """Not 0.0 — that would say the site failed everything."""
    assert audit_score([CheckResult("a", "", CRITICAL, NOT_MEASURED)]) is None


# --------------------------------------------------------------------------
# the grade, and what it refuses to hide
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "grade"),
    [(100.0, "A"), (90.0, "A"), (80.0, "B"), (65.0, "C"), (45.0, "D"), (10.0, "F")],
)
def test_grade_bands(score, grade):
    assert audit_grade(score, critical_failures=0) == grade


def test_one_critical_failure_caps_the_grade_at_c():
    assert audit_grade(95.0, critical_failures=1) == "C"


def test_two_critical_failures_are_an_f_however_good_the_average():
    """The reason the cap exists.

    A site can block every AI crawler AND be noindex, then bank enough minor
    passes to average into a B. A number that can hide the only two things that
    matter is worse than no number.
    """
    assert audit_grade(95.0, critical_failures=2) == "F"


def test_the_cap_never_improves_a_grade():
    assert audit_grade(30.0, critical_failures=1) == "F"


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------


def test_a_healthy_site_grades_well():
    outcome = audit(crawl(), robots_allowing_all())
    assert outcome.status == seo_audit.STATUS_OK
    assert outcome.grade == "A"
    assert outcome.critical_failures == ()


def test_blocking_a_retrieval_crawler_is_a_critical_failure():
    outcome = audit(crawl(), robots_blocking("OAI-SearchBot"))
    assert status_of(outcome, "ai_crawler_access") == FAIL
    assert outcome.grade == "C"  # capped, despite everything else passing


def test_blocking_only_training_crawlers_is_a_warning_not_a_failure():
    """Opting out of training is a legitimate choice, not a broken site."""
    outcome = audit(crawl(), robots_blocking("GPTBot", "ClaudeBot", "CCBot"))
    assert status_of(outcome, "ai_crawler_access") == WARN
    assert outcome.critical_failures == ()


def test_an_unreadable_robots_txt_is_not_a_failure():
    outcome = audit(crawl(), RobotsReport(measured=False))
    assert status_of(outcome, "ai_crawler_access") == NOT_MEASURED
    assert outcome.critical_failures == ()


def test_a_client_rendered_page_fails_because_crawlers_do_not_run_javascript():
    outcome = audit(crawl(page(server_text_chars=120)), robots_allowing_all())
    assert status_of(outcome, "server_rendered_content") == FAIL
    assert status_of(outcome, "thin_content") == FAIL
    # Two criticals -> F, which is the honest answer for a site an AI crawler
    # sees as an empty div.
    assert outcome.grade == "F"


def test_noindex_is_a_critical_failure():
    outcome = audit(crawl(page(meta_robots="noindex, nofollow")), robots_allowing_all())
    assert status_of(outcome, "indexable") == FAIL


def test_noindex_is_caught_in_the_header_too():
    outcome = audit(crawl(page(x_robots_tag="noindex")), robots_allowing_all())
    assert status_of(outcome, "indexable") == FAIL


def test_plain_http_is_a_critical_failure():
    outcome = audit(crawl(page(final_url="http://example.com/")), robots_allowing_all())
    assert status_of(outcome, "https") == FAIL


def test_missing_organization_schema_is_reported():
    outcome = audit(crawl(page(jsonld_types=())), robots_allowing_all())
    assert status_of(outcome, "organization_schema") == FAIL


def test_schema_without_an_entity_type_is_only_a_warning():
    outcome = audit(crawl(page(jsonld_types=("BreadcrumbList",))), robots_allowing_all())
    assert status_of(outcome, "organization_schema") == WARN


def test_several_h1s_are_a_warning_and_none_is_a_failure():
    assert status_of(audit(crawl(page(h1_count=3)), robots_allowing_all()), "h1_present") == WARN
    assert status_of(audit(crawl(page(h1_count=0)), robots_allowing_all()), "h1_present") == FAIL


def test_a_page_with_no_images_is_not_applicable_rather_than_passing():
    """"Nothing to check" and "checked and fine" are different claims."""
    outcome = audit(crawl(page(image_count=0, images_missing_alt=0)), robots_allowing_all())
    assert status_of(outcome, "image_alt") == NOT_APPLICABLE


def test_mostly_missing_alt_text_fails_but_only_as_a_minor():
    outcome = audit(crawl(page(image_count=10, images_missing_alt=9)), robots_allowing_all())
    assert status_of(outcome, "image_alt") == FAIL
    assert outcome.grade in ("A", "B")  # a minor cannot sink the grade


def test_a_crawl_with_no_pages_reports_no_crawl_rather_than_a_zero():
    outcome = audit(CrawlResult(text="", pages=()), robots_allowing_all())
    assert outcome.status == seo_audit.STATUS_NO_CRAWL
    assert outcome.score is None
    assert outcome.grade is None


def test_every_check_declares_a_known_severity_and_status():
    outcome = audit(crawl(), robots_allowing_all())
    assert outcome.checks
    for check in outcome.checks:
        assert check.severity in (CRITICAL, IMPORTANT, MINOR)
        assert check.status in (PASS, WARN, FAIL, NOT_MEASURED, NOT_APPLICABLE)
        assert check.title


def test_check_ids_are_unique_so_a_stored_row_is_unambiguous():
    ids = [c.check_id for c in audit(crawl(), robots_allowing_all()).checks]
    assert len(ids) == len(set(ids))
