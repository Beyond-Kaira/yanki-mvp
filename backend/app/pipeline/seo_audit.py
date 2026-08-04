"""The SEO / AI-readiness audit: can an answer engine read this site at all?

The GEO score says whether AI engines name a company. SERP visibility says
whether search results do. Neither explains **why** when the answer is no, and
"why" is the only part a customer can act on. This audit is that explanation, and
it is computed almost entirely from the crawl discovery has already paid for.

What makes it worth shipping rather than being one more generic SEO checklist:

* **It leads with the checks that are about AI specifically.** Whether AI
  crawlers are allowed in (``robots.py``), whether the page says anything without
  JavaScript, and whether there is enough text to quote. A site can pass every
  classic SEO audit ever written and still be invisible to an answer engine for
  those three reasons, none of which a classic tool looks at.
* **It is honest about which checks are just SEO.** ``meta_description``,
  ``canonical`` and ``open_graph`` are worth having and are mostly not about AI.
  They are weighted as minor and their descriptions say so, because dressing
  classic hygiene up as AI-critical is how this category earned its reputation.

**The headline is a grade, not a number, and that is deliberate.** ``geo_score``
is a *measurement* — a counted ratio (ADR-11). An audit score is a *rubric*: the
weights are editorial choices, not observations. A weighted average also averages
a fatal problem away — a site that is ``noindex`` and blocks every AI crawler can
still collect enough minor passes to look like a C. So the grade is **capped by
critical failures**, and the failing checks are the real output.

The three-state discipline of ADR-28 applies per check. ``not_measured`` (we
could not read the input) and ``not_applicable`` (the check does not apply here)
are dropped from **both** sides of the ratio, exactly as an unreadable SERP page
is dropped from its denominator. A check we could not evaluate is never a
failure, and never a free pass.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from app.pipeline import robots
from app.pipeline.discovery import (
    TIMEOUT_SECONDS,
    USER_AGENT,
    CrawlResult,
    PageAudit,
    _guard_request,
)
from app.pipeline.robots import RobotsReport

logger = logging.getLogger(__name__)

# Per-check outcomes.
PASS = "pass"
WARN = "warn"
FAIL = "fail"
NOT_MEASURED = "not_measured"
NOT_APPLICABLE = "not_applicable"

# Severity doubles as the weight. Three tiers rather than per-check coefficients:
# thirty hand-tuned numbers are unauditable and drift, three are publishable.
CRITICAL = "critical"
IMPORTANT = "important"
MINOR = "minor"

_WEIGHTS = {CRITICAL: 5, IMPORTANT: 3, MINOR: 1}
_CREDIT = {PASS: 1.0, WARN: 0.5, FAIL: 0.0}

# Below this many characters of SERVER-rendered text, a page has nothing an
# answer engine could quote. Matches discovery's own SPA threshold, because it is
# the same judgement: this page needs JavaScript to say anything.
THIN_CONTENT_FAIL = 800
THIN_CONTENT_WARN = 2_500

STATUS_OK = "ok"
STATUS_NO_CRAWL = "no_crawl"
STATUS_ERROR = "error"

_GRADE_BANDS = ((90.0, "A"), (75.0, "B"), (60.0, "C"), (40.0, "D"))


@dataclass(frozen=True)
class CheckResult:
    """One audit check, its verdict, and the evidence behind it."""

    check_id: str
    title: str
    severity: str
    status: str
    detail: str = ""
    evidence: str = ""

    @property
    def weight(self) -> int:
        return _WEIGHTS.get(self.severity, 1)

    @property
    def evaluated(self) -> bool:
        return self.status in _CREDIT


@dataclass(frozen=True)
class AuditOutcome:
    status: str
    score: float | None
    grade: str | None
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)

    @property
    def failed(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if c.status == FAIL)

    @property
    def critical_failures(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.failed if c.severity == CRITICAL)


def audit_score(checks) -> float | None:
    """Weighted pass-ratio over the checks we could actually evaluate.

    Pure and publishable (ADR-11). ``not_measured`` and ``not_applicable`` are in
    neither sum, so the score is always "the fraction of the weighted checks we
    could read", never inflated by counting an unreadable input either way.
    ``None`` when nothing was evaluable — not ``0.0``, which would mean the
    opposite.
    """
    evaluated = [c for c in checks if c.evaluated]
    total = sum(c.weight for c in evaluated)
    if total <= 0:
        return None
    earned = sum(c.weight * _CREDIT[c.status] for c in evaluated)
    return round(100.0 * earned / total, 1)


def audit_grade(score: float | None, critical_failures: int) -> str | None:
    """Band the score, then let critical failures cap it.

    The cap is the point. Without it a site that blocks every AI crawler and is
    ``noindex`` can still bank enough minor passes to grade C, and a number that
    can hide the only thing that matters is worse than no number. The rule is
    published rather than hidden: one critical failure caps at C, two or more
    cap at F.
    """
    if score is None:
        return None
    grade = "F"
    for threshold, letter in _GRADE_BANDS:
        if score >= threshold:
            grade = letter
            break
    if critical_failures >= 2:
        return "F"
    if critical_failures == 1 and grade in ("A", "B"):
        return "C"
    return grade


def _home(pages) -> PageAudit | None:
    for page in pages:
        if page.is_home:
            return page
    return pages[0] if pages else None


def _check_ai_crawlers(robots: RobotsReport) -> CheckResult:
    title = "AI crawlers can read the site"
    if not robots.measured:
        return CheckResult(
            "ai_crawler_access", title, CRITICAL, NOT_MEASURED,
            "We could not read robots.txt, so we cannot say what it permits.",
        )
    blocked_now = robots.blocked_retrieval
    blocked_training = robots.blocked_training
    if blocked_now:
        names = ", ".join(f"{c.token} ({c.product})" for c in blocked_now)
        return CheckResult(
            "ai_crawler_access", title, CRITICAL, FAIL,
            "robots.txt blocks crawlers that answer engines use to retrieve and "
            "cite pages. While that stands, this site cannot appear in their "
            "answers — no amount of content or ranking changes that.",
            f"Blocked: {names}",
        )
    if blocked_training:
        names = ", ".join(f"{c.token} ({c.product})" for c in blocked_training)
        return CheckResult(
            "ai_crawler_access", title, CRITICAL, WARN,
            "Live answer crawlers are allowed, but training crawlers are blocked. "
            "That is a legitimate choice; the cost is that the models learn less "
            "about this company over time.",
            f"Blocked from training: {names}",
        )
    where = "There is no robots.txt, so nothing is blocked." if robots.absent else (
        "robots.txt allows every AI crawler we check."
    )
    return CheckResult("ai_crawler_access", title, CRITICAL, PASS, where)


def _check_indexable(home: PageAudit) -> CheckResult:
    title = "Page is not marked noindex"
    haystack = f"{home.meta_robots} {home.x_robots_tag}".casefold()
    if "noindex" in haystack:
        return CheckResult(
            "indexable", title, CRITICAL, FAIL,
            "The homepage tells search engines not to index it. It cannot be "
            "retrieved or cited by the engines that answer from a search index.",
            f"meta robots: {home.meta_robots or '-'} | X-Robots-Tag: {home.x_robots_tag or '-'}",
        )
    return CheckResult("indexable", title, CRITICAL, PASS, "Nothing blocks indexing.")


def _check_server_rendered(home: PageAudit) -> CheckResult:
    title = "Content is in the HTML, not just JavaScript"
    if home.server_text_chars < THIN_CONTENT_FAIL:
        return CheckResult(
            "server_rendered_content", title, CRITICAL, FAIL,
            "The server sends almost no readable text — the page is assembled in "
            "the browser. Most AI crawlers do not run JavaScript, so they see an "
            "empty page even though a human sees a full one.",
            f"{home.server_text_chars} characters of server-rendered text",
        )
    return CheckResult(
        "server_rendered_content", title, CRITICAL, PASS,
        "The server sends the content, so a crawler that does not run JavaScript "
        "can still read it.",
        f"{home.server_text_chars} characters of server-rendered text",
    )


def _check_thin_content(home: PageAudit) -> CheckResult:
    title = "There is enough text to quote"
    chars = home.server_text_chars
    if chars < THIN_CONTENT_FAIL:
        status, detail = FAIL, (
            "An answer engine can only quote what exists as text. There is not "
            "enough here for it to say anything about this company."
        )
    elif chars < THIN_CONTENT_WARN:
        status, detail = WARN, (
            "There is some text, but not much. Engines tend to cite the page that "
            "explains the most."
        )
    else:
        status, detail = PASS, "There is substantial text for an engine to draw on."
    return CheckResult("thin_content", title, CRITICAL, status, detail, f"{chars} characters")


def _check_https(home: PageAudit) -> CheckResult:
    title = "Served over HTTPS"
    scheme = urlparse(home.final_url or home.url).scheme
    if scheme == "https":
        return CheckResult("https", title, CRITICAL, PASS, "The site is served over HTTPS.")
    if not scheme:
        return CheckResult("https", title, CRITICAL, NOT_MEASURED, "No final URL was recorded.")
    return CheckResult(
        "https", title, CRITICAL, FAIL,
        "The site is served over plain HTTP. Crawlers deprioritise or skip it.",
        f"final URL scheme: {scheme}",
    )


_ENTITY_TYPES = {"organization", "corporation", "localbusiness", "onlinestore", "product"}


def _check_org_schema(pages) -> CheckResult:
    title = "Structured data identifies the company"
    types = {t.casefold() for page in pages for t in page.jsonld_types}
    if types & _ENTITY_TYPES:
        found = ", ".join(sorted(types & _ENTITY_TYPES))
        return CheckResult(
            "organization_schema", title, IMPORTANT, PASS,
            "schema.org markup names the company as an entity, which is how a "
            "model attaches facts to the right business.",
            f"types: {found}",
        )
    if types:
        return CheckResult(
            "organization_schema", title, IMPORTANT, WARN,
            "There is structured data, but none of it identifies the company "
            "itself (Organization, LocalBusiness or Product).",
            f"types found: {', '.join(sorted(types))}",
        )
    return CheckResult(
        "organization_schema", title, IMPORTANT, FAIL,
        "There is no schema.org markup. A model has to infer who this company is "
        "from prose, and will confuse it with similarly named ones.",
    )


def _check_same_as(pages) -> CheckResult:
    title = "Structured data links to the wider web"
    links = {url for page in pages for url in page.jsonld_same_as}
    if links:
        return CheckResult(
            "entity_links_sameas", title, IMPORTANT, PASS,
            "sameAs links let a model corroborate this company against sources it "
            "already trusts.",
            ", ".join(sorted(links)[:5]),
        )
    return CheckResult(
        "entity_links_sameas", title, IMPORTANT, FAIL,
        "No sameAs links. Nothing connects this site to the company's Wikipedia, "
        "LinkedIn or social profiles, so a model has only this site's word for who "
        "it is.",
    )


def _check_title(home: PageAudit) -> CheckResult:
    title = "Homepage has a title"
    if home.title:
        return CheckResult(
            "title_present", title, IMPORTANT, PASS,
            "The title is what an engine usually shows as the citation label.",
            home.title,
        )
    return CheckResult(
        "title_present", title, IMPORTANT, FAIL,
        "The homepage has no <title>, so an engine citing it has no label to use.",
    )


def _check_h1(home: PageAudit) -> CheckResult:
    title = "Homepage has exactly one H1"
    if home.h1_count == 1:
        return CheckResult(
            "h1_present", title, IMPORTANT, PASS,
            "A single H1 gives engines a clean passage boundary to quote from.",
        )
    if home.h1_count == 0:
        return CheckResult(
            "h1_present", title, IMPORTANT, FAIL,
            "There is no H1. Answer engines chunk pages by heading to pick a "
            "passage; without one they extract worse quotes, or none.",
        )
    return CheckResult(
        "h1_present", title, IMPORTANT, WARN,
        "There are several H1s, so the page's main subject is ambiguous.",
        f"{home.h1_count} H1 elements",
    )


def _check_lang(home: PageAudit) -> CheckResult:
    title = "Page declares its language"
    if home.lang:
        return CheckResult("lang_declared", title, IMPORTANT, PASS, "", f"lang=\"{home.lang}\"")
    return CheckResult(
        "lang_declared", title, IMPORTANT, FAIL,
        "<html> has no lang attribute, so an engine answering in a particular "
        "language cannot tell whether this page belongs in that answer.",
    )


def _check_meta_description(home: PageAudit) -> CheckResult:
    title = "Homepage has a meta description"
    detail = (
        "Mostly classic SEO: AI answers write their own summary and rarely lift "
        "this, though some engines fall back to it for a snippet."
    )
    if home.meta_description:
        return CheckResult("meta_description", title, MINOR, PASS, detail, home.meta_description)
    return CheckResult("meta_description", title, MINOR, FAIL, detail)


def _check_canonical(home: PageAudit) -> CheckResult:
    title = "Homepage declares a canonical URL"
    detail = (
        "Mostly classic SEO. The mild AI cost of missing it is that duplicate "
        "URLs split the signal and the wrong one gets cited."
    )
    if home.canonical:
        return CheckResult("canonical", title, MINOR, PASS, detail, home.canonical)
    return CheckResult("canonical", title, MINOR, FAIL, detail)


def _check_open_graph(home: PageAudit) -> CheckResult:
    title = "Open Graph tags are present"
    detail = (
        "Mostly social previews. Some engines fall back to og:title or "
        "og:site_name when naming a source."
    )
    if home.og_keys:
        return CheckResult("open_graph", title, MINOR, PASS, detail, ", ".join(home.og_keys[:6]))
    return CheckResult("open_graph", title, MINOR, FAIL, detail)


def _check_sitemap(robots: RobotsReport) -> CheckResult:
    title = "A sitemap is advertised"
    detail = "Mostly a classic discovery aid; it helps crawlers find deeper pages."
    if not robots.measured:
        return CheckResult("sitemap", title, MINOR, NOT_MEASURED, "robots.txt was unreadable.")
    if robots.sitemaps:
        return CheckResult("sitemap", title, MINOR, PASS, detail, robots.sitemaps[0])
    return CheckResult(
        "sitemap", title, MINOR, FAIL, f"{detail} robots.txt advertises none."
    )


def _check_image_alt(pages) -> CheckResult:
    title = "Images have alt text"
    total = sum(p.image_count for p in pages)
    missing = sum(p.images_missing_alt for p in pages)
    if total == 0:
        return CheckResult(
            "image_alt", title, MINOR, NOT_APPLICABLE, "The crawled pages have no images."
        )
    evidence = f"{missing} of {total} images have no alt text"
    if missing == 0:
        return CheckResult("image_alt", title, MINOR, PASS, "", evidence)
    if missing * 2 <= total:
        return CheckResult("image_alt", title, MINOR, WARN, "", evidence)
    return CheckResult(
        "image_alt", title, MINOR, FAIL,
        "Most images carry no alt text, so whatever they say is invisible to a "
        "text-only reader.",
        evidence,
    )


def run_checks(crawl: CrawlResult, robots: RobotsReport) -> tuple[CheckResult, ...]:
    """Every check, in reporting order: what blocks AI first, hygiene last."""
    home = _home(crawl.pages)
    if home is None:
        return ()
    pages = crawl.pages
    return (
        _check_ai_crawlers(robots),
        _check_indexable(home),
        _check_server_rendered(home),
        _check_thin_content(home),
        _check_https(home),
        _check_org_schema(pages),
        _check_same_as(pages),
        _check_title(home),
        _check_h1(home),
        _check_lang(home),
        _check_meta_description(home),
        _check_canonical(home),
        _check_sitemap(robots),
        _check_open_graph(home),
        _check_image_alt(pages),
    )


def audit(crawl: CrawlResult, robots: RobotsReport) -> AuditOutcome:
    """Score one crawl. Pure — every fetch has already happened."""
    checks = run_checks(crawl, robots)
    if not checks:
        return AuditOutcome(STATUS_NO_CRAWL, None, None, ())
    score = audit_score(checks)
    critical = sum(1 for c in checks if c.status == FAIL and c.severity == CRITICAL)
    return AuditOutcome(STATUS_OK, score, audit_grade(score, critical), checks)


def run_audit(session, analysis, crawl: CrawlResult) -> AuditOutcome:
    """Audit one crawl and persist a row per check. Never raises.

    Fail-open for the same reason the SERP pass is (ADR-28): by the time this
    runs the analysis has already paid for a crawl, and an audit defect must cost
    the run its grade and nothing else. The one extra fetch — ``robots.txt`` —
    goes through discovery's own SSRF-guarded client.
    """
    from app.db.models import SeoCheck

    try:
        with httpx.Client(
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            event_hooks={"request": [_guard_request]},
        ) as client:
            report = robots.fetch(client, analysis.url)
        outcome = audit(crawl, report)
    except Exception:
        logger.warning("seo audit failed for %s", getattr(analysis, "url", "?"), exc_info=True)
        return AuditOutcome(STATUS_ERROR, None, None, ())

    for check in outcome.checks:
        session.add(
            SeoCheck(
                analysis_id=analysis.id,
                check_id=check.check_id,
                title=check.title,
                severity=check.severity,
                status=check.status,
                detail=check.detail or None,
                evidence=check.evidence or None,
            )
        )
    session.flush()
    return outcome
