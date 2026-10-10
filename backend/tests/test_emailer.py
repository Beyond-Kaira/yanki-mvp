"""Emailer unit tests (P5.13): the Resend POST is env-gated and fail-open.

Uses respx to intercept the httpx call so nothing ever leaves the process — no
live call to resend.com is made or possible here.
"""

from __future__ import annotations

import uuid

import httpx
import respx

from app.config import Settings
from app.db.models import Analysis
from app.services.emailer import (
    RESEND_ENDPOINT,
    send_email,
    send_run_alert,
    send_waitlist_emails,
)

_ON = dict(emails_enabled=True, resend_api_key="re_test_key", email_from="from@yanki.test")


@respx.mock
def test_send_email_success_posts_to_resend_and_returns_true():
    route = respx.post(RESEND_ENDPOINT).mock(return_value=httpx.Response(200, json={"id": "e1"}))
    settings = Settings(**_ON)

    assert send_email("joiner@example.com", "Hi", "body", settings) is True

    assert route.called
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer re_test_key"
    body = request.content.decode()
    assert "joiner@example.com" in body
    assert "from@yanki.test" in body


@respx.mock
def test_send_email_swallows_http_500_and_returns_false():
    route = respx.post(RESEND_ENDPOINT).mock(return_value=httpx.Response(500))
    settings = Settings(**_ON)

    # A 500 must be swallowed (no raise) and reported as False.
    assert send_email("joiner@example.com", "Hi", "body", settings) is False
    assert route.called


@respx.mock
def test_send_email_disabled_is_a_noop_and_makes_no_call():
    route = respx.post(RESEND_ENDPOINT).mock(return_value=httpx.Response(200))

    # Disabled (default) — never touches the network.
    assert send_email("joiner@example.com", "Hi", "body", Settings(emails_enabled=False)) is False
    # Enabled but no key — also a no-op.
    assert send_email("joiner@example.com", "Hi", "body", Settings(emails_enabled=True)) is False
    assert not route.called


@respx.mock
def test_thank_you_email_invites_a_first_free_analysis_with_the_site_url():
    route = respx.post(RESEND_ENDPOINT).mock(return_value=httpx.Response(200, json={"id": "e1"}))
    settings = Settings(**_ON)

    send_waitlist_emails("joiner@example.com", 1, settings)

    # The first send is the thank-you to the joiner; assert on stable substrings
    # (subject + the public site URL to run a first analysis), not the full body.
    thank_you = route.calls[0].request.content.decode()
    assert "Thanks for joining the Yanki waitlist" in thank_you
    assert "https://yanki.beyondkaira.com" in thank_you


def _alert_link(kind: str, settings: Settings) -> str:
    """Capture the single line the run alert writes for the results-page link."""
    captured: list[str] = []

    with respx.mock:
        route = respx.post(RESEND_ENDPOINT).mock(return_value=httpx.Response(200, json={"id": "e"}))
        analysis = Analysis(
            id=uuid.uuid4(),
            url="https://example.com",
            status="done",
            kind=kind,
            brand="Acme",
            category="crm",
            geo_score=0.5,
        )
        send_run_alert(analysis, settings)
        captured.append(route.calls.last.request.content.decode())
    return captured[0]


def test_run_alert_link_is_kind_aware():
    settings = Settings(**_ON, notify_email="ops@yanki.test")

    mvp_body = _alert_link("mvp", settings)
    assert "https://yanki.beyondkaira.com/ai-visibility?analysis=" in mvp_body
    assert "/checker/" not in mvp_body

    checker_body = _alert_link("checker", settings)
    assert "https://yanki.beyondkaira.com/checker/" in checker_body
    assert "/ai-visibility?analysis=" not in checker_body
