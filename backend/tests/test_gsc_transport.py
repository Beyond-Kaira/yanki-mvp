"""The httpx adapter google-auth fetches Google's signing certificates through.

This file exists because of a specific hazard. Every other test in this feature
injects ``MockGoogleOAuthProvider``, so none of them execute a single line of
``app/gsc/transport.py`` — and it is the one piece of security-adjacent
plumbing here that was written by hand rather than taken from a library. Code
that only runs in production is code that is first exercised in production.

``respx`` intercepts httpx, so the adapter runs for real against a fake network.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.gsc.transport import HttpxRequest

CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"


@respx.mock
def test_it_returns_status_headers_and_body_in_the_shape_google_auth_reads():
    respx.get(CERTS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"keys": []},
            headers={"cache-control": "max-age=3600"},
        )
    )

    response = HttpxRequest()(CERTS_URL)

    # google-auth reads exactly these three attributes and nothing else.
    assert response.status == 200
    assert response.data == b'{"keys":[]}'
    assert response.headers["cache-control"] == "max-age=3600"


@respx.mock
def test_a_non_200_is_passed_through_rather_than_raised():
    """google-auth inspects the status itself; raising here would hide it."""

    respx.get(CERTS_URL).mock(return_value=httpx.Response(503, text="unavailable"))

    response = HttpxRequest()(CERTS_URL)

    assert response.status == 503


@respx.mock
def test_it_sends_the_method_body_and_headers_it_was_given():
    route = respx.post("https://example.test/token").mock(return_value=httpx.Response(200, json={}))

    HttpxRequest()(
        "https://example.test/token",
        method="POST",
        body=b"grant_type=refresh_token",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    request = route.calls.last.request
    assert request.method == "POST"
    assert request.content == b"grant_type=refresh_token"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"


@respx.mock
def test_a_transport_failure_surfaces_as_an_httpx_error():
    """google-auth wraps this into its own TransportError, which the adapter
    above turns into GoogleIdentityError. What matters is that it is not
    swallowed into a falsy response."""

    respx.get(CERTS_URL).mock(side_effect=httpx.ConnectError("no route to host"))

    with pytest.raises(httpx.HTTPError):
        HttpxRequest()(CERTS_URL)


@respx.mock
def test_the_per_call_timeout_wins_over_the_default():
    route = respx.get(CERTS_URL).mock(return_value=httpx.Response(200, json={}))

    HttpxRequest(timeout=30.0)(CERTS_URL, timeout=1.0)

    assert route.calls.last.request.extensions["timeout"] == {
        "connect": 1.0,
        "pool": 1.0,
        "read": 1.0,
        "write": 1.0,
    }
