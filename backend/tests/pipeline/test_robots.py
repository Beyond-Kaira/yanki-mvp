"""robots.txt reading: which AI crawlers a site actually lets in.

The distinction these tests exist to pin is retrieval vs training. Telling a
customer their AI visibility is broken because they declined to be training data
would be wrong and alarmist; telling them nothing when they have blocked the
crawler that feeds ChatGPT Search would be worse.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.pipeline import robots

ROBOTS_URL = "https://example.com/robots.txt"
SITE = "https://example.com/"


def _fetch(**response_kwargs) -> robots.RobotsReport:
    with httpx.Client() as client:
        return robots.fetch(client, SITE)


@respx.mock
def test_no_robots_txt_means_everything_is_allowed():
    """A 404 is an answer, not a failure to get one."""
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(404))

    report = _fetch()

    assert report.measured is True
    assert report.absent is True
    assert all(c.allowed for c in report.crawlers)
    assert report.blocked_retrieval == ()


@respx.mock
def test_an_unreachable_robots_txt_is_not_measured():
    """Reporting "blocked" because a fetch flaked would fabricate the worst case."""
    respx.get(ROBOTS_URL).mock(side_effect=httpx.ConnectError("refused"))

    report = _fetch()

    assert report.measured is False
    assert report.crawlers == ()


@respx.mock
def test_a_forbidden_robots_txt_is_not_measured():
    """The file exists and we are not allowed to read it — so we do not guess."""
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(403))

    assert _fetch().measured is False


@respx.mock
def test_an_empty_robots_txt_allows_everything():
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(200, text="   \n\n"))

    report = _fetch()

    assert report.measured is True
    assert all(c.allowed for c in report.crawlers)


@respx.mock
def test_a_blanket_disallow_blocks_every_crawler():
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /\n")
    )

    report = _fetch()

    assert all(c.allowed is False for c in report.crawlers)
    assert report.blocked_retrieval  # answers lost today
    assert report.blocked_training  # and presence eroded over time


@respx.mock
def test_blocking_only_training_crawlers_costs_no_answers_today():
    """The nuance the whole module exists for.

    Opting out of training is a legitimate choice. It must not be reported as
    "you cannot appear in AI answers", because that is a different claim.
    """
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(
            200,
            text=(
                "User-agent: GPTBot\nDisallow: /\n\n"
                "User-agent: ClaudeBot\nDisallow: /\n\n"
                "User-agent: CCBot\nDisallow: /\n"
            ),
        )
    )

    report = _fetch()

    assert {c.token for c in report.blocked_training} >= {"GPTBot", "ClaudeBot", "CCBot"}
    assert report.blocked_retrieval == ()


@respx.mock
def test_blocking_a_retrieval_crawler_is_what_costs_answers():
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: OAI-SearchBot\nDisallow: /\n")
    )

    report = _fetch()

    assert [c.token for c in report.blocked_retrieval] == ["OAI-SearchBot"]
    assert report.blocked_training == ()


@respx.mock
def test_blocking_googlebot_is_treated_as_an_ai_retrieval_block():
    """Google documents Googlebot as the control for AI Overviews.

    There is no separate opt-in, so a Googlebot block removes a site from
    Google's AI answers — which is exactly the sort of thing a classic SEO
    audit would file under "crawlability" and never connect to AI visibility.
    """
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: Googlebot\nDisallow: /\n")
    )

    assert "Googlebot" in {c.token for c in _fetch().blocked_retrieval}


@respx.mock
def test_an_agent_that_ignores_robots_is_never_counted_as_blocked():
    """Perplexity documents that Perplexity-User generally ignores robots.txt.

    Counting it would tell a customer they had successfully blocked something
    they have not.
    """
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /\n")
    )

    report = _fetch()

    blocked = {c.token for c in report.blocked_retrieval}
    assert "Perplexity-User" not in blocked
    # It is still reported, just not scored.
    assert any(c.token == "Perplexity-User" and c.allowed is False for c in report.crawlers)


@respx.mock
def test_sitemaps_are_read_out_of_robots_txt():
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(
            200,
            text="Sitemap: https://example.com/sitemap.xml\nUser-agent: *\nDisallow:\n",
        )
    )

    assert _fetch().sitemaps == ("https://example.com/sitemap.xml",)


@pytest.mark.parametrize("token", ["anthropic-ai", "Claude-Web", "Bytespider"])
def test_tokens_we_cannot_stand_behind_are_not_in_the_list(token):
    """Two are deprecated by Anthropic; one has no vendor documentation at all.

    A list padded with plausible-looking tokens looks more thorough and is less
    true.
    """
    assert token not in {c.token for c in robots.AI_CRAWLERS}
