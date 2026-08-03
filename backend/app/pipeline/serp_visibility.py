"""SERP visibility: does the company show up in ordinary search results?

The GEO score answers "do AI engines name this company". This answers the same
question on the surface buyers still use next to them — a search results page —
by reading an **open-source metasearch instance** (SearXNG) instead of a paid
SERP API. It is the roadmap's admitted gap, closed with a container the operator
runs rather than a per-query invoice.

Four properties this module is responsible for.

* **The queries never name the brand.** They are built from
  ``prompts.topic_pool`` — literally the same pool, with the same brand filter,
  that the scored questions come from — and every finished query is re-checked
  with ``prompts.leaks_brand``. Searching for a brand and then counting the brand
  is a self-fulfilling score on a results page exactly as it is in an answer
  (ADR-27), and here the temptation is stronger because "brand + category" is
  what an SEO tool would obviously query.

* **A hit is a domain match *or* a text match.** A search result is mostly a URL
  and two lines of snippet, so the company's own site ranking is the strongest
  signal available and needs no text at all — which also makes this the one place
  in the pipeline that can see a company the LLM panel never names. A directory
  or listicle that names the company in its snippet counts too, through the very
  same ``footprint.detect`` used on LLM answers, so both surfaces agree on what
  "a mention" means.

* **An unmeasurable page is never scored as a miss.** See ``serp/base.py``: a
  live instance regularly answers ``200 OK`` with nothing, because every upstream
  engine rate-limited it. Those queries are dropped from the denominator rather
  than counted as zeroes, so ``serp_score`` is always ``hits / queries we could
  actually read``.

* **Nothing here can fail the job.** By the time this runs, the analysis has paid
  for a crawl, a KYC call and up to ``max_responses_per_job`` LLM calls. A search
  instance that is down, slow, or serving HTML because its operator forgot to
  enable the JSON format must cost the run its SERP number and nothing else — the
  same fail-open stance ``services/emailer`` takes (ADR-25).

It runs inside the existing **footprint** step rather than as a seventh pipeline
step. That is not squeamishness about the progress contract: footprint is the
step that asks "where does this brand actually appear", and this is that question
asked of a second corpus. ``current_step`` and the progress mapping are untouched,
so no frontend or SPEC change rides along with the feature.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from app.db.models import SerpCheck
from app.pipeline import footprint
from app.pipeline.prompts import brand_keys, leaks_brand, topic_pool
from app.pipeline.sanitize import clean_values, normalize_key
from app.serp.base import SerpPage, SerpResult, SerpSource, SerpUnavailable

logger = logging.getLogger(__name__)

# Recorded on ``analyses.serp_status``. Anything other than OK means the score is
# null and the UI must say "not measured" rather than draw a zero.
STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NO_TOPICS = "no_topics"

# How the brand was found on the page.
VIA_DOMAIN = "domain"
VIA_TEXT = "text"

DEFAULT_QUERY_COUNT = 6

MAX_SNIPPET_CHARS = 300

# Query shapes, cycled. Deliberately keyword-shaped rather than the full
# questions ``prompts`` builds: people type "best CRM software" into a search
# box and ask an assistant "Which CRM software would you recommend, and why?".
# Feeding a search engine the question form measures how well the engine handles
# questions, which is not what we are trying to find out.
_QUERY_SHAPES = (
    "best {topic}",
    "top {topic} companies",
    "{topic} comparison",
    "{topic} reviews",
    "{topic} alternatives",
    "how to choose {topic}",
)

# Slotted in second when the profile knows where the company operates. Local
# intent is most of commercial search, and a Turkish manufacturer that ranks
# nowhere globally may well own its home results.
_LOCATION_SHAPE = "best {topic} in {location}"


@dataclass(frozen=True)
class SerpHit:
    """Where the brand first appeared on one results page."""

    rank: int
    url: str
    snippet: str
    via: str


@dataclass(frozen=True)
class SerpOutcome:
    """What one analysis's SERP pass produced, ready to write onto the row."""

    status: str
    source: str
    hits: int
    queries: int
    score: float | None


def _location(kyc) -> str:
    locations = clean_values(getattr(kyc, "locations", []), max_items=25, max_chars=120)
    return locations[0] if locations else ""


def _shapes(location: str) -> tuple[str, ...]:
    if not location:
        return _QUERY_SHAPES
    return (*_QUERY_SHAPES[:1], _LOCATION_SHAPE, *_QUERY_SHAPES[1:])


def build_queries(kyc, count: int = DEFAULT_QUERY_COUNT) -> list[str]:
    """``count`` distinct, brand-free search queries for this profile.

    Shape and topic advance on different strides for the reason
    ``prompts._question_specs`` does it: walking both with one index means a
    profile with exactly as many topics as shapes produces that many queries out
    of a possible product of the two. Returns fewer than ``count`` — possibly
    none — rather than repeating itself or letting the brand through.
    """
    if count <= 0:
        return []
    topics = [topic.text for topic in topic_pool(kyc)]
    if not topics:
        return []

    location = _location(kyc)
    shapes = _shapes(location)
    keys = brand_keys(kyc)

    queries: list[str] = []
    seen: set[str] = set()
    lap = len(shapes)
    step = 0
    max_steps = count * lap * len(topics) + count
    while len(queries) < count and step < max_steps:
        shape = shapes[step % lap]
        topic = topics[(step + step // lap) % len(topics)]
        step += 1
        text = shape.format(topic=topic, location=location)
        key = normalize_key(text)
        if not key or key in seen:
            continue
        if leaks_brand(text, keys):
            continue
        seen.add(key)
        queries.append(text)
    return queries


def _host(url: str) -> str:
    """A URL's comparison host: lowercased, no ``www.``; ``""`` if there isn't one.

    Only ``http``/``https`` URLs have a host worth comparing. The check is not
    pedantry: a checker analysis carries a synthetic ``checker://<brand>`` url,
    and ``urlparse`` reads that brand as a hostname — which would then match any
    search result served from a host of the same name and hand the run a domain
    hit it never earned.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https"):
        return ""
    host = (parsed.hostname or "").strip().lower()
    return host[4:] if host.startswith("www.") else host


def site_hosts(url: str) -> frozenset[str]:
    """The host(s) that count as the company's own site.

    Empty for a checker run, whose ``checker://`` url names no site — those runs
    are measured on text matches alone, which is correct: we were given a brand
    name, not a domain, so we have no business claiming a domain is theirs.
    """
    host = _host(url or "")
    return frozenset({host}) if host else frozenset()


def _is_own_site(result_url: str, hosts: frozenset[str]) -> bool:
    """True when a result points at the company's own site or a subdomain of it."""
    host = _host(result_url)
    if not host:
        return False
    return any(host == owned or host.endswith(f".{owned}") for owned in hosts)


def _snippet(result: SerpResult) -> str:
    parts = [part for part in (result.title, result.content) if part]
    return " — ".join(parts)[:MAX_SNIPPET_CHARS]


def detect(page: SerpPage, kyc, hosts: frozenset[str]) -> SerpHit | None:
    """The brand's best (lowest-rank) appearance on one page, or ``None``.

    Results are walked in rank order and the first match of either kind wins, so
    the recorded rank answers "how far down the page before a buyer sees them",
    which is the only rank a visibility number can honestly claim.
    """
    for result in page.results:
        if _is_own_site(result.url, hosts):
            return SerpHit(result.rank, result.url, _snippet(result), VIA_DOMAIN)
        hit, snippet = footprint.detect(f"{result.title} {result.content}".strip(), kyc)
        if hit:
            return SerpHit(result.rank, result.url, snippet or _snippet(result), VIA_TEXT)
    return None


def serp_score(hits: int, measured: int) -> float | None:
    """``hits / measured``; ``None`` when nothing could be measured.

    Pure, like ``scoring.geo_score`` (ADR-11) — but returning ``None`` rather
    than ``0.0`` on an empty denominator, because the two mean opposite things
    here. Zero responses to score is a bug; zero *measurable* search pages is a
    search instance having a bad day, and reporting 0.0 for it would tell a
    customer they rank nowhere when we simply did not look.
    """
    if measured <= 0:
        return None
    return hits / measured


def run_serp(session, analysis, kyc, source: SerpSource, settings) -> SerpOutcome:
    """Run the SERP pass for one analysis, persisting a row per query.

    Never raises: every failure mode collapses into a status the row can carry.
    The caller is responsible for not calling this at all when the registry
    hands back no source — a run with SERP switched off leaves every ``serp_*``
    column null, which is a different statement from "we tried and failed".
    """
    count = getattr(settings, "serp_query_count", DEFAULT_QUERY_COUNT)
    queries = build_queries(kyc, count)
    if not queries:
        # A profile with no category-like topic gives us nothing a buyer would
        # ever type. Same judgement ``require_usable`` makes before the paid
        # fan-out: refuse to produce a number rather than search for "solutions".
        return SerpOutcome(STATUS_NO_TOPICS, source.name, 0, 0, None)

    hosts = site_hosts(getattr(analysis, "url", "") or "")
    hits = 0
    measured = 0

    def record_unreadable(query: str, page: SerpPage | None) -> None:
        """Persist a query we could not read, so the gap is visible as a gap.

        These rows carry ``hit=None`` and are excluded from the score. Writing
        them at all is the point: a missing row would look like a query we never
        ran, and this one we ran and could not use.
        """
        refused = ", ".join(page.unresponsive_engines) if page else ""
        session.add(
            SerpCheck(
                analysis_id=analysis.id,
                query=query,
                source=source.name,
                hit=None,
                result_count=len(page.results) if page else 0,
                unresponsive_engines=refused or None,
            )
        )
        session.flush()

    for query in queries:
        try:
            page = source.search(query)
        except SerpUnavailable as exc:
            # The expected failure: the instance is down, slow, or serving HTML.
            # Carry on — one flaky query should not lose the other five.
            logger.info("serp query could not be read (query=%r): %s", query, exc)
            record_unreadable(query, None)
            continue
        except Exception:
            # Fail-open in the strong sense (ADR-28). By the time this runs, the
            # analysis has paid for a crawl, a KYC call and the whole LLM panel,
            # so ANY defect in a search source — not just the one failure mode we
            # anticipated — costs this run its SERP number and nothing else.
            # Logged with a traceback rather than swallowed: an adapter bug must
            # still be visible in the worker log even though it is not fatal.
            logger.warning("serp source raised unexpectedly (query=%r)", query, exc_info=True)
            record_unreadable(query, None)
            continue

        if not page.measurable:
            record_unreadable(query, page)
            continue

        found = detect(page, kyc, hosts)
        measured += 1
        if found is not None:
            hits += 1
        session.add(
            SerpCheck(
                analysis_id=analysis.id,
                query=query,
                source=source.name,
                hit=found is not None,
                rank=found.rank if found else None,
                matched_url=found.url if found else None,
                matched_snippet=found.snippet if found else None,
                matched_via=found.via if found else None,
                result_count=len(page.results),
                unresponsive_engines=", ".join(page.unresponsive_engines) or None,
            )
        )
        session.flush()

    score = serp_score(hits, measured)
    if score is None:
        # Unreachable, or reached and unreadable — either way the honest report
        # is "not measured", and the per-query rows say which it was.
        return SerpOutcome(STATUS_UNAVAILABLE, source.name, hits, measured, None)
    return SerpOutcome(STATUS_OK, source.name, hits, measured, score)
