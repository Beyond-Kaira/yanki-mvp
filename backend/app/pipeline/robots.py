"""Which AI crawlers a site's ``robots.txt`` lets in.

This is the most AI-specific thing the audit can say, and the one no classic SEO
tool says at all: a site that disallows the crawler feeding an answer engine
**cannot appear in that engine's answers**. It is absent by construction rather
than by ranking, and every other number the product reports is downstream of it.

Two distinctions make the claim honest rather than alarmist.

* **Retrieval vs training.** Blocking ``GPTBot`` opts out of *training* — it does
  not remove you from live ChatGPT answers. ``OAI-SearchBot`` is what governs
  those. Reporting them as one number would tell a customer their visibility is
  broken when they have simply declined to be training data, which is a
  legitimate and common choice. Retrieval blocks cost you answers *today*;
  training blocks erode presence in the model's parametric memory over time.
* **Whether the vendor honours it at all.** Perplexity documents that
  ``Perplexity-User`` generally ignores ``robots.txt``. Telling someone they have
  successfully blocked it would be false, so it is reported but never scored.

``Googlebot`` is in the list for a reason that surprises people: Google's own
documentation says robots.txt for ``Googlebot`` is the control for AI features,
and that there is no additional opt-in for AI Overviews. Blocking Googlebot
therefore removes you from Google's AI answers. ``Google-Extended``, despite the
name, is a training/grounding control only and does not affect them.

Deliberately not listed: ``anthropic-ai`` and ``Claude-Web`` (both deprecated by
Anthropic), and ``Bytespider`` (no vendor documentation exists, and it is widely
reported to ignore robots.txt — a token we cannot stand behind is worse than no
token). Padding the list would make the check look thorough and be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx

# What a blocked crawler actually costs you.
ROLE_RETRIEVAL = "retrieval"
ROLE_TRAINING = "training"

MAX_ROBOTS_BYTES = 512_000


@dataclass(frozen=True)
class Crawler:
    token: str
    product: str
    role: str
    # False for agents the vendor says may ignore robots.txt. Reported, never
    # scored: a directive that will not be obeyed is not a control.
    honors_robots: bool = True


# Verified against vendor documentation, not folklore. Each entry is a token a
# publisher would actually write in robots.txt.
AI_CRAWLERS: tuple[Crawler, ...] = (
    # --- retrieval: blocking these costs you answers today -------------------
    Crawler("OAI-SearchBot", "ChatGPT Search", ROLE_RETRIEVAL),
    Crawler("ChatGPT-User", "ChatGPT (user visits)", ROLE_RETRIEVAL),
    Crawler("Claude-SearchBot", "Claude search", ROLE_RETRIEVAL),
    Crawler("Claude-User", "Claude (user visits)", ROLE_RETRIEVAL),
    Crawler("PerplexityBot", "Perplexity", ROLE_RETRIEVAL),
    Crawler("Perplexity-User", "Perplexity (user visits)", ROLE_RETRIEVAL, honors_robots=False),
    # Google's index is what AI Overviews and AI Mode answer from; Google
    # documents Googlebot as the control, with no separate AI opt-in.
    Crawler("Googlebot", "Google Search + AI Overviews", ROLE_RETRIEVAL),
    Crawler("bingbot", "Bing + Microsoft Copilot", ROLE_RETRIEVAL),
    Crawler("Applebot", "Siri / Spotlight", ROLE_RETRIEVAL),
    # --- training: blocking these erodes presence over time -------------------
    Crawler("GPTBot", "OpenAI model training", ROLE_TRAINING),
    Crawler("ClaudeBot", "Anthropic model training", ROLE_TRAINING),
    Crawler("Google-Extended", "Gemini training / grounding", ROLE_TRAINING),
    Crawler("Applebot-Extended", "Apple Intelligence training", ROLE_TRAINING),
    Crawler("CCBot", "Common Crawl (a major training corpus)", ROLE_TRAINING),
    Crawler("meta-externalagent", "Meta AI", ROLE_TRAINING),
    Crawler("Amazonbot", "Amazon / Alexa", ROLE_TRAINING),
)


@dataclass(frozen=True)
class CrawlerAccess:
    """One crawler's verdict. ``allowed`` is ``None`` when we could not read
    ``robots.txt`` at all — which is not the same as being blocked."""

    token: str
    product: str
    role: str
    allowed: bool | None
    honors_robots: bool = True


@dataclass(frozen=True)
class RobotsReport:
    """What ``robots.txt`` said, and whether we managed to ask."""

    # True when we know the policy — including the case where there is no file.
    measured: bool
    # True when the site has no robots.txt at all (a 404 is an answer: allow all).
    absent: bool = False
    sitemaps: tuple[str, ...] = ()
    crawlers: tuple[CrawlerAccess, ...] = ()

    @property
    def blocked_retrieval(self) -> tuple[CrawlerAccess, ...]:
        """Blocked crawlers whose block actually costs answers now."""
        return tuple(
            c
            for c in self.crawlers
            if c.allowed is False and c.role == ROLE_RETRIEVAL and c.honors_robots
        )

    @property
    def blocked_training(self) -> tuple[CrawlerAccess, ...]:
        return tuple(
            c
            for c in self.crawlers
            if c.allowed is False and c.role == ROLE_TRAINING and c.honors_robots
        )


def _sitemaps(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for line in text.splitlines():
        name, _, value = line.partition(":")
        if name.strip().casefold() == "sitemap":
            url = value.strip()
            if url and url not in found:
                found.append(url)
    return tuple(found)


def evaluate(text: str) -> tuple[CrawlerAccess, ...]:
    """Ask ``robots.txt`` about each crawler's access to ``/``.

    Uses the stdlib parser rather than a hand-rolled one — it already implements
    the group selection, ``Allow`` precedence and case-insensitive agent matching
    that RFC 9309 specifies, and a bespoke parser here would be a second thing to
    get subtly wrong. It is fed the text we already fetched: ``RobotFileParser``
    would otherwise re-fetch through ``urllib``, bypassing the SSRF guard every
    other fetch in this pipeline goes through.
    """
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return tuple(
        CrawlerAccess(
            token=crawler.token,
            product=crawler.product,
            role=crawler.role,
            allowed=parser.can_fetch(crawler.token, "/"),
            honors_robots=crawler.honors_robots,
        )
        for crawler in AI_CRAWLERS
    )


def _allow_all() -> tuple[CrawlerAccess, ...]:
    return tuple(
        CrawlerAccess(c.token, c.product, c.role, True, c.honors_robots) for c in AI_CRAWLERS
    )


def fetch(client: httpx.Client, site_url: str) -> RobotsReport:
    """Read ``/robots.txt`` and report what it permits.

    The three outcomes are kept apart on purpose (ADR-28's discipline, one layer
    down). A **404** is an answer — there is no policy, so everything is allowed.
    A **transport error** is not an answer, and reporting "blocked" because a
    fetch flaked would fabricate the worst case, which is exactly the sin this
    codebase organises against. A **200** is parsed.
    """
    try:
        response = client.get(urljoin(site_url, "/robots.txt"))
    except httpx.HTTPError:
        return RobotsReport(measured=False)

    if response.status_code in (401, 403):
        # The file exists but we are not allowed to read it. We cannot say what
        # it permits, so we do not guess.
        return RobotsReport(measured=False)
    if response.status_code >= 400:
        return RobotsReport(measured=True, absent=True, crawlers=_allow_all())
    if response.status_code != 200:
        return RobotsReport(measured=False)

    text = response.text[:MAX_ROBOTS_BYTES]
    if not text.strip():
        # An empty robots.txt permits everything, same as no file at all.
        return RobotsReport(measured=True, absent=False, crawlers=_allow_all())
    return RobotsReport(
        measured=True,
        absent=False,
        sitemaps=_sitemaps(text),
        crawlers=evaluate(text),
    )
