"""The real Google adapter, without Google.

The mock provider proves the *service* handles each outcome. This file proves
the real adapter produces those outcomes — which is a different claim, and the
one that decides what happens in production. Two halves:

* ``exchange_code`` over ``respx``: a real httpx request against a fake network,
  asserting both what is sent and that no failure mode leaks Google's response
  text into an exception message.
* ``_identity_from_claims`` directly: the checks ``verify_oauth2_token`` does
  **not** make. Signature, audience and expiry belong to the library and are not
  re-tested here; issuer, nonce presence, subject, email and ``email_verified``
  are ours, and each one is a way a token can be genuine and still not be an
  identity we may act on.

No network, no key, no credential.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import GOOGLE_OAUTH_SCOPES, Settings
from app.gsc.base import GoogleIdentityError, GoogleOAuthError
from app.gsc.google import TOKEN_ENDPOINT, GoogleOAuthClient, _identity_from_claims
from app.services.token_crypto import generate_encryption_key

REDIRECT_URI = "http://localhost:8141/api/v1/integrations/google-search-console/callback"
CLIENT_SECRET = "test-client-secret-do-not-log"


@pytest.fixture()
def client() -> GoogleOAuthClient:
    return GoogleOAuthClient(
        Settings(
            gsc_enabled=True,
            google_oauth_client_id="test-client.apps.googleusercontent.com",
            google_oauth_client_secret=CLIENT_SECRET,
            google_oauth_redirect_uri=REDIRECT_URI,
            token_encryption_key=generate_encryption_key(),
        )
    )


def _claims(**overrides) -> dict:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "test-client.apps.googleusercontent.com",
        "sub": "1234567890",
        "email": "owner@example.test",
        "email_verified": True,
        "nonce": "the-nonce-from-this-attempt",
    }
    claims.update(overrides)
    return claims


# --------------------------------------------------------------------------
# authorization_url
# --------------------------------------------------------------------------


def test_the_authorization_url_carries_no_client_secret(client):
    url = client.authorization_url(state="s", nonce="n", code_challenge="c")

    assert CLIENT_SECRET not in url
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")


def test_the_authorization_url_requests_only_the_agreed_scopes(client):
    url = client.authorization_url(state="s", nonce="n", code_challenge="c")

    from urllib.parse import parse_qs, urlsplit

    assert parse_qs(urlsplit(url).query)["scope"][0].split() == list(GOOGLE_OAUTH_SCOPES)


# --------------------------------------------------------------------------
# exchange_code
# --------------------------------------------------------------------------


@respx.mock
def test_a_successful_exchange_sends_the_verifier_and_returns_the_tokens(client):
    route = respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "at",
                "refresh_token": "rt",
                "id_token": "idt",
                "scope": "openid email",
                "expires_in": 3599,
            },
        )
    )

    tokens = client.exchange_code(code="the-code", code_verifier="the-verifier")

    assert tokens.access_token == "at"
    assert tokens.refresh_token == "rt"
    assert tokens.id_token == "idt"
    assert tokens.scope == "openid email"

    sent = dict(pair.split("=", 1) for pair in route.calls.last.request.content.decode().split("&"))
    assert sent["code"] == "the-code"
    assert sent["code_verifier"] == "the-verifier"
    assert sent["grant_type"] == "authorization_code"


@respx.mock
def test_a_missing_refresh_token_is_reported_as_absent_not_invented(client):
    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(
            200, json={"access_token": "at", "id_token": "idt", "scope": "openid"}
        )
    )

    tokens = client.exchange_code(code="c", code_verifier="v")

    assert tokens.refresh_token is None


@respx.mock
def test_a_rejected_code_raises_without_quoting_googles_body(client):
    """Google's error body echoes attacker-influenced input. It is never read."""

    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "<script>alert(1)</script>",
            },
        )
    )

    with pytest.raises(GoogleOAuthError) as caught:
        client.exchange_code(code="c", code_verifier="v")

    message = str(caught.value)
    assert "script" not in message
    assert "invalid_grant" not in message
    assert "400" in message


@respx.mock
def test_an_unreachable_token_endpoint_raises_a_domain_error(client):
    respx.post(TOKEN_ENDPOINT).mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(GoogleOAuthError) as caught:
        client.exchange_code(code="c", code_verifier="v")

    assert "no route" not in str(caught.value)


@respx.mock
def test_a_non_json_body_raises_a_domain_error(client):
    respx.post(TOKEN_ENDPOINT).mock(return_value=httpx.Response(200, text="<html>oops</html>"))

    with pytest.raises(GoogleOAuthError):
        client.exchange_code(code="c", code_verifier="v")


@respx.mock
@pytest.mark.parametrize("missing", ["id_token", "access_token"])
def test_a_token_response_missing_a_required_field_raises(client, missing):
    payload = {"access_token": "at", "id_token": "idt", "scope": "openid"}
    payload.pop(missing)
    respx.post(TOKEN_ENDPOINT).mock(return_value=httpx.Response(200, json=payload))

    with pytest.raises(GoogleOAuthError):
        client.exchange_code(code="c", code_verifier="v")


# --------------------------------------------------------------------------
# The claim checks the library does not make
# --------------------------------------------------------------------------


def test_a_complete_token_yields_the_identity_and_carries_the_nonce_out():
    identity = _identity_from_claims(_claims())

    assert identity.subject == "1234567890"
    assert identity.email == "owner@example.test"
    # Returned rather than compared here: only the service layer holds the hash.
    assert identity.nonce == "the-nonce-from-this-attempt"


@pytest.mark.parametrize("issuer", ["accounts.google.com", "https://accounts.google.com"])
def test_both_issuer_spellings_google_uses_are_accepted(issuer):
    assert _identity_from_claims(_claims(iss=issuer)).subject == "1234567890"


@pytest.mark.parametrize(
    "issuer",
    ["https://accounts.google.com.evil.test", "https://login.microsoftonline.com", ""],
)
def test_any_other_issuer_is_refused(issuer):
    with pytest.raises(GoogleIdentityError):
        _identity_from_claims(_claims(iss=issuer))


def test_a_token_without_a_nonce_is_refused():
    """An ID token with no nonce cannot be bound to an attempt, so it is not one."""

    claims = _claims()
    del claims["nonce"]

    with pytest.raises(GoogleIdentityError):
        _identity_from_claims(claims)


@pytest.mark.parametrize("claim", ["sub", "email"])
def test_a_token_missing_an_identity_claim_is_refused(claim):
    claims = _claims()
    del claims[claim]

    with pytest.raises(GoogleIdentityError):
        _identity_from_claims(claims)


@pytest.mark.parametrize("value", [False, "true", None, 1])
def test_an_email_that_is_not_verifiably_verified_is_refused(value):
    """`is not True` on purpose: the string "true" is not a verified email."""

    with pytest.raises(GoogleIdentityError):
        _identity_from_claims(_claims(email_verified=value))
