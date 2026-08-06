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

import inspect
import json as jsonlib
from urllib.parse import quote

import httpx
import pytest
import respx

import app.gsc.google as google_module
from app.config import GOOGLE_OAUTH_SCOPES, Settings
from app.gsc.base import (
    GoogleAccessForbidden,
    GoogleAuthorizationRevoked,
    GoogleIdentityError,
    GoogleOAuthError,
    GoogleRateLimited,
    GoogleResponseInvalid,
)
from app.gsc.google import (
    SEARCH_CONSOLE_BASE,
    TOKEN_ENDPOINT,
    GoogleOAuthClient,
    _identity_from_claims,
)
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


# --------------------------------------------------------------------------
# refresh_access_token
# --------------------------------------------------------------------------


@respx.mock
def test_a_refresh_returns_an_access_token_and_sends_no_code(client):
    route = respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"access_token": "fresh", "expires_in": 3599})
    )

    issued = client.refresh_access_token(refresh_token="stored-token")

    assert issued.access_token == "fresh"
    assert issued.expires_in == 3599
    sent = dict(pair.split("=", 1) for pair in route.calls.last.request.content.decode().split("&"))
    assert sent["grant_type"] == "refresh_token"
    assert sent["refresh_token"] == "stored-token"
    assert "code" not in sent


@respx.mock
@pytest.mark.parametrize("status_code", [400, 401])
def test_a_refused_refresh_is_a_revocation_not_an_outage(client, status_code):
    """invalid_grant has no retry that helps — only the user reconnecting does."""

    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(status_code, json={"error": "invalid_grant"})
    )

    with pytest.raises(GoogleAuthorizationRevoked):
        client.refresh_access_token(refresh_token="revoked")


@respx.mock
def test_a_refresh_response_without_a_token_is_invalid_not_empty(client):
    respx.post(TOKEN_ENDPOINT).mock(return_value=httpx.Response(200, json={"expires_in": 10}))

    with pytest.raises(GoogleResponseInvalid):
        client.refresh_access_token(refresh_token="t")


@respx.mock
def test_a_refresh_never_quotes_googles_body(client):
    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(400, json={"error_description": "token=SECRET-LEAKED"})
    )

    with pytest.raises(GoogleAuthorizationRevoked) as caught:
        client.refresh_access_token(refresh_token="t")

    assert "SECRET-LEAKED" not in str(caught.value)


# --------------------------------------------------------------------------
# list_properties
# --------------------------------------------------------------------------


@respx.mock
def test_properties_are_returned_with_the_bearer_token_attached(client):
    route = respx.get(f"{SEARCH_CONSOLE_BASE}/sites").mock(
        return_value=httpx.Response(
            200,
            json={
                "siteEntry": [
                    {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
                    {"siteUrl": "https://example.com/", "permissionLevel": "siteFullUser"},
                ]
            },
        )
    )

    properties = client.list_properties(access_token="at-123")

    assert [p.site_url for p in properties] == ["sc-domain:example.com", "https://example.com/"]
    assert route.calls.last.request.headers["authorization"] == "Bearer at-123"


@respx.mock
def test_an_account_with_no_properties_is_empty_not_an_error(client):
    """Google omits the key entirely. Reading that as a failure would be wrong."""

    respx.get(f"{SEARCH_CONSOLE_BASE}/sites").mock(return_value=httpx.Response(200, json={}))

    assert client.list_properties(access_token="at") == ()


@respx.mock
def test_entries_without_a_site_url_are_skipped_and_odd_levels_survive(client):
    respx.get(f"{SEARCH_CONSOLE_BASE}/sites").mock(
        return_value=httpx.Response(
            200,
            json={
                "siteEntry": [
                    {"permissionLevel": "siteOwner"},
                    "not-an-object",
                    {"siteUrl": "https://ok.test/"},
                    {"siteUrl": "https://odd.test/", "permissionLevel": 7},
                ]
            },
        )
    )

    properties = client.list_properties(access_token="at")

    assert [p.site_url for p in properties] == ["https://ok.test/", "https://odd.test/"]
    # A non-string level becomes "", which is safely not siteOwner.
    assert properties[1].permission_level == ""


@respx.mock
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, GoogleAuthorizationRevoked),
        (403, GoogleAccessForbidden),
        (429, GoogleRateLimited),
        (500, GoogleOAuthError),
        (503, GoogleOAuthError),
    ],
)
def test_each_google_status_maps_to_its_own_domain_error(client, status_code, expected):
    respx.get(f"{SEARCH_CONSOLE_BASE}/sites").mock(
        return_value=httpx.Response(status_code, json={"error": {"message": "leaky detail"}})
    )

    with pytest.raises(expected) as caught:
        client.list_properties(access_token="at")

    assert "leaky detail" not in str(caught.value)


@respx.mock
def test_a_rate_limit_carries_retry_after_from_the_header_only(client):
    respx.get(f"{SEARCH_CONSOLE_BASE}/sites").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "42"}, json={})
    )

    with pytest.raises(GoogleRateLimited) as caught:
        client.list_properties(access_token="at")

    assert caught.value.retry_after_seconds == 42


@respx.mock
@pytest.mark.parametrize("header", ["not-a-number", "Wed, 21 Oct 2026 07:28:00 GMT", ""])
def test_an_unparseable_retry_after_is_simply_absent(client, header):
    respx.get(f"{SEARCH_CONSOLE_BASE}/sites").mock(
        return_value=httpx.Response(429, headers={"Retry-After": header}, json={})
    )

    with pytest.raises(GoogleRateLimited) as caught:
        client.list_properties(access_token="at")

    assert caught.value.retry_after_seconds is None


# --------------------------------------------------------------------------
# query_search_analytics
# --------------------------------------------------------------------------


def _analytics_url(site_url: str) -> str:
    return f"{SEARCH_CONSOLE_BASE}/sites/{quote(site_url, safe='')}/searchAnalytics/query"


@respx.mock
def test_the_site_url_is_fully_quoted_into_the_path(client):
    """sc-domain: and https:// both die unquoted — safe='' or the call 404s."""

    route = respx.post(_analytics_url("sc-domain:example.com")).mock(
        return_value=httpx.Response(200, json={"rows": []})
    )

    client.query_search_analytics(
        access_token="at",
        site_url="sc-domain:example.com",
        start_date="2026-07-01",
        end_date="2026-07-28",
    )

    assert route.called
    assert "sc-domain%3Aexample.com" in str(route.calls.last.request.url)


@respx.mock
def test_the_query_body_is_bounded_and_asks_for_finalized_data(client):
    route = respx.post(_analytics_url("https://example.com/")).mock(
        return_value=httpx.Response(200, json={"rows": []})
    )

    client.query_search_analytics(
        access_token="at",
        site_url="https://example.com/",
        start_date="2026-07-01",
        end_date="2026-07-28",
        dimensions=("query",),
        row_limit=10,
    )

    assert jsonlib.loads(route.calls.last.request.content) == {
        "startDate": "2026-07-01",
        "endDate": "2026-07-28",
        "rowLimit": 10,
        "dataState": "final",
        "dimensions": ["query"],
    }


@respx.mock
def test_a_query_with_no_dimensions_omits_the_key(client):
    route = respx.post(_analytics_url("https://example.com/")).mock(
        return_value=httpx.Response(200, json={"rows": []})
    )

    client.query_search_analytics(
        access_token="at",
        site_url="https://example.com/",
        start_date="2026-07-01",
        end_date="2026-07-28",
    )

    assert "dimensions" not in jsonlib.loads(route.calls.last.request.content)


@respx.mock
def test_rows_are_coerced_into_typed_metrics(client):
    respx.post(_analytics_url("https://example.com/")).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {
                        "keys": ["shoes"],
                        "clicks": 10,
                        "impressions": 100,
                        "ctr": 0.1,
                        "position": 3.5,
                    }
                ]
            },
        )
    )

    rows = client.query_search_analytics(
        access_token="at",
        site_url="https://example.com/",
        start_date="2026-07-01",
        end_date="2026-07-28",
        dimensions=("query",),
    )

    assert len(rows) == 1
    assert rows[0].keys == ("shoes",)
    assert rows[0].clicks == 10.0
    assert isinstance(rows[0].clicks, float)


@respx.mock
@pytest.mark.parametrize(
    "bad_row",
    [
        pytest.param({"keys": ["q"], "impressions": 1, "ctr": 0.1, "position": 1}, id="no-clicks"),
        pytest.param(
            {"keys": ["q"], "clicks": "10", "impressions": 1, "ctr": 0.1, "position": 1},
            id="string-metric",
        ),
        pytest.param(
            {"keys": ["q"], "clicks": True, "impressions": 1, "ctr": 0.1, "position": 1},
            id="bool-metric",
        ),
        pytest.param(
            {"keys": [], "clicks": 1, "impressions": 1, "ctr": 0.1, "position": 1},
            id="missing-dimension-key",
        ),
        pytest.param(
            {"keys": ["a", "b"], "clicks": 1, "impressions": 1, "ctr": 0.1, "position": 1},
            id="too-many-keys",
        ),
        pytest.param("not-an-object", id="not-an-object"),
    ],
)
def test_a_row_that_will_not_parse_is_dropped_not_zero_filled(client, bad_row):
    """A zero is a claim about performance. A dropped row is not."""

    good = {"keys": ["ok"], "clicks": 1, "impressions": 2, "ctr": 0.5, "position": 1.0}
    respx.post(_analytics_url("https://example.com/")).mock(
        return_value=httpx.Response(200, json={"rows": [bad_row, good]})
    )

    rows = client.query_search_analytics(
        access_token="at",
        site_url="https://example.com/",
        start_date="2026-07-01",
        end_date="2026-07-28",
        dimensions=("query",),
    )

    assert [row.keys for row in rows] == [("ok",)]


@respx.mock
def test_an_answer_with_no_rows_is_empty_not_an_error(client):
    respx.post(_analytics_url("https://example.com/")).mock(
        return_value=httpx.Response(200, json={})
    )

    rows = client.query_search_analytics(
        access_token="at",
        site_url="https://example.com/",
        start_date="2026-07-01",
        end_date="2026-07-28",
    )

    assert rows == ()


@respx.mock
def test_an_unreadable_analytics_body_is_a_shape_error_not_an_outage(client):
    respx.post(_analytics_url("https://example.com/")).mock(
        return_value=httpx.Response(200, text="<html>nope</html>")
    )

    with pytest.raises(GoogleResponseInvalid):
        client.query_search_analytics(
            access_token="at",
            site_url="https://example.com/",
            start_date="2026-07-01",
            end_date="2026-07-28",
        )


@respx.mock
def test_a_timeout_is_an_availability_error_that_names_no_url(client):
    respx.post(_analytics_url("https://example.com/")).mock(
        side_effect=httpx.ReadTimeout("timed out talking to searchconsole.googleapis.com")
    )

    with pytest.raises(GoogleOAuthError) as caught:
        client.query_search_analytics(
            access_token="at",
            site_url="https://example.com/",
            start_date="2026-07-01",
            end_date="2026-07-28",
        )

    assert "searchconsole.googleapis.com" not in str(caught.value)


def test_this_adapter_can_reach_no_google_analytics_api():
    """A structural check, because scope creep here would be silent."""

    source = inspect.getsource(google_module)

    assert "analytics.readonly" not in source
    assert "analyticsdata" not in source
    assert "analyticsadmin" not in source
