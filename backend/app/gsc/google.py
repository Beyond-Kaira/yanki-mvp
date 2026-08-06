"""The real Google OAuth 2.0 / OIDC adapter.

Two of the three operations are plain HTTP against documented endpoints, so they
are plain ``httpx``: building an authorization URL is query-string assembly, and
exchanging a code is one form POST. Neither needs a client library, which is why
``google-auth-oauthlib`` and ``google-api-python-client`` are not dependencies.

The third is not. Verifying an ID token means checking an RS256 signature
against a rotating JWKS, then the issuer, the audience and the expiry — and a
hand-rolled version of that is how "verification" quietly becomes "base64
decode". That one operation uses Google's own library.

Nothing in this module logs. The values it handles are an authorization code, a
refresh token and an ID token, and there is no level at which any of them is
safe to write down.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

import httpx
from google.auth.exceptions import GoogleAuthError as _LibraryAuthError
from google.oauth2 import id_token as google_id_token

from app.config import GOOGLE_OAUTH_SCOPES, Settings
from app.gsc.base import (
    GoogleAccessForbidden,
    GoogleAccessToken,
    GoogleAuthorizationRevoked,
    GoogleIdentity,
    GoogleIdentityError,
    GoogleOAuthError,
    GoogleProperty,
    GoogleRateLimited,
    GoogleResponseInvalid,
    GoogleTokens,
    SearchAnalyticsRow,
)
from app.gsc.transport import HttpxRequest

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
SEARCH_CONSOLE_BASE = "https://searchconsole.googleapis.com/webmasters/v3"

# Google mints ID tokens under both spellings and treats them as equivalent.
_ACCEPTED_ISSUERS = ("accounts.google.com", "https://accounts.google.com")

_TOKEN_TIMEOUT_SECONDS = 15.0
# Search Analytics is the slow one — a wide query over a large property takes
# seconds. Bounded anyway, because this runs inside a user's request and an
# unbounded wait there is an outage that looks like a hang.
_API_TIMEOUT_SECONDS = 30.0


class GoogleOAuthClient:
    """The production :class:`~app.gsc.base.GoogleOAuthProvider`."""

    name = "google"

    def __init__(self, settings: Settings) -> None:
        self._client_id = settings.google_oauth_client_id
        self._client_secret = settings.google_oauth_client_secret.get_secret_value()
        self._redirect_uri = settings.google_oauth_redirect_uri
        self._clock_skew_seconds = settings.jwt_clock_skew_seconds

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_OAUTH_SCOPES),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            # Without this Google returns no refresh token at all, and a
            # connection that cannot be refreshed is a connection that breaks in
            # an hour.
            "access_type": "offline",
            "include_granted_scopes": "true",
            # `consent` costs a consent screen on every reconnect, and buys the
            # guarantee that a refresh token comes back — Google otherwise omits
            # it whenever it decides the grant already exists, which would leave
            # a reconnect unable to repair a revoked token. `select_account`
            # keeps a user with several Google accounts from being silently
            # bound to whichever one their browser happens to be signed into.
            "prompt": "consent select_account",
        }
        return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"

    def exchange_code(self, *, code: str, code_verifier: str) -> GoogleTokens:
        try:
            response = httpx.post(
                TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self._redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
                timeout=_TOKEN_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            # str(exc) can carry the request URL; the message is fixed instead.
            raise GoogleOAuthError("google token endpoint was unreachable") from exc

        if response.status_code != httpx.codes.OK:
            # Google's body describes why the *code* failed and is echoed from
            # attacker-influenced input. It is not read, not logged, not
            # returned — only the status class matters here.
            raise GoogleOAuthError(f"google token endpoint returned {response.status_code}")

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise GoogleOAuthError("google token endpoint returned a non-JSON body") from exc

        if not isinstance(payload, dict):
            raise GoogleOAuthError("google token endpoint returned an unexpected body")

        id_token_value = payload.get("id_token")
        access_token = payload.get("access_token")
        if not isinstance(id_token_value, str) or not id_token_value:
            raise GoogleOAuthError("google token response carried no id_token")
        if not isinstance(access_token, str) or not access_token:
            raise GoogleOAuthError("google token response carried no access_token")

        refresh_token = payload.get("refresh_token")
        scope = payload.get("scope")
        expires_in = payload.get("expires_in")

        return GoogleTokens(
            access_token=access_token,
            refresh_token=refresh_token
            if isinstance(refresh_token, str) and refresh_token
            else None,
            id_token=id_token_value,
            scope=scope if isinstance(scope, str) else "",
            expires_in=expires_in if isinstance(expires_in, int) else None,
        )

    def verify_identity(self, *, id_token: str) -> GoogleIdentity:
        try:
            claims: Any = google_id_token.verify_oauth2_token(
                id_token,
                HttpxRequest(),
                # Pinning the audience to our own client id is what stops an ID
                # token minted for a different application from being accepted.
                self._client_id,
                clock_skew_in_seconds=self._clock_skew_seconds,
            )
        except (_LibraryAuthError, ValueError) as exc:
            raise GoogleIdentityError("google id token failed verification") from exc

        if not isinstance(claims, dict):
            raise GoogleIdentityError("google id token carried no claims")

        return _identity_from_claims(claims)

    # ----------------------------------------------------------------------
    # Search Console
    # ----------------------------------------------------------------------

    def refresh_access_token(self, *, refresh_token: str) -> GoogleAccessToken:
        try:
            response = httpx.post(
                TOKEN_ENDPOINT,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Accept": "application/json"},
                timeout=_TOKEN_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise GoogleOAuthError("google token endpoint was unreachable") from exc

        if response.status_code in (httpx.codes.BAD_REQUEST, httpx.codes.UNAUTHORIZED):
            # Google says `invalid_grant` here for a revoked, expired or
            # password-reset-invalidated refresh token. The distinction between
            # its sub-reasons is not actionable; "reconnect" is the answer to
            # all of them.
            raise GoogleAuthorizationRevoked("google refused the stored refresh token")

        _raise_for_api_status(response)

        payload = _json_object(response, what="token")

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GoogleResponseInvalid("google refresh response carried no access_token")

        expires_in = payload.get("expires_in")
        return GoogleAccessToken(
            access_token=access_token,
            expires_in=expires_in if isinstance(expires_in, int) else None,
        )

    def list_properties(self, *, access_token: str) -> tuple[GoogleProperty, ...]:
        try:
            response = httpx.get(
                f"{SEARCH_CONSOLE_BASE}/sites",
                headers=_bearer(access_token),
                timeout=_API_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise GoogleOAuthError("google search console was unreachable") from exc

        _raise_for_api_status(response)
        payload = _json_object(response, what="site list")

        entries = payload.get("siteEntry", [])
        if entries is None:
            # An account with no properties at all. Google omits the key rather
            # than sending an empty list, and reading that as an error would
            # turn "you have no properties" into "something broke".
            return ()
        if not isinstance(entries, list):
            raise GoogleResponseInvalid("google returned an unreadable site list")

        properties: list[GoogleProperty] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            site_url = entry.get("siteUrl")
            permission_level = entry.get("permissionLevel")
            if not isinstance(site_url, str) or not site_url:
                continue
            properties.append(
                GoogleProperty(
                    site_url=site_url,
                    # An unfamiliar permission string is reported as-is rather
                    # than mapped to a guess; the service decides what is
                    # offerable, and "" is safely not siteOwner.
                    permission_level=(
                        permission_level if isinstance(permission_level, str) else ""
                    ),
                )
            )

        return tuple(properties)

    def query_search_analytics(
        self,
        *,
        access_token: str,
        site_url: str,
        start_date: str,
        end_date: str,
        dimensions: tuple[str, ...] = (),
        row_limit: int = 25,
    ) -> tuple[SearchAnalyticsRow, ...]:
        body: dict[str, Any] = {
            "startDate": start_date,
            "endDate": end_date,
            "rowLimit": row_limit,
            # Finalized data only. Google's "fresh" data for recent days is
            # revised afterwards, and a number that changes when you reload it
            # is worse than a number that arrives three days late.
            "dataState": "final",
        }
        if dimensions:
            body["dimensions"] = list(dimensions)

        try:
            response = httpx.post(
                # siteUrl goes in the path, so `sc-domain:` and `https://` both
                # need full quoting — safe="" or the colon and slashes survive
                # and the request 404s.
                f"{SEARCH_CONSOLE_BASE}/sites/{quote(site_url, safe='')}/searchAnalytics/query",
                headers=_bearer(access_token),
                json=body,
                timeout=_API_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise GoogleOAuthError("google search console was unreachable") from exc

        _raise_for_api_status(response)
        payload = _json_object(response, what="search analytics")

        rows = payload.get("rows", [])
        if rows is None:
            return ()
        if not isinstance(rows, list):
            raise GoogleResponseInvalid("google returned unreadable search analytics rows")

        parsed: list[SearchAnalyticsRow] = []
        for row in rows:
            converted = _search_analytics_row(row, expected_keys=len(dimensions))
            # A row that will not parse is dropped, not zero-filled. A zero is a
            # claim about a query's performance; a missing row is not.
            if converted is not None:
                parsed.append(converted)

        return tuple(parsed)


def _bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}


def _raise_for_api_status(response: httpx.Response) -> None:
    """Map Google's status codes onto exceptions, without reading the body.

    The body of a Google error echoes request content and can carry the token
    that was rejected, so it is never parsed, logged or forwarded. The status
    line alone decides, and each case maps to a different thing the caller can
    do: reconnect, choose another property, wait, or give up for now.
    """

    status = response.status_code
    if status == httpx.codes.OK:
        return

    if status == httpx.codes.UNAUTHORIZED:
        raise GoogleAuthorizationRevoked("google rejected the access token")
    if status == httpx.codes.FORBIDDEN:
        raise GoogleAccessForbidden("google refused access to this property")
    if status == httpx.codes.TOO_MANY_REQUESTS:
        raise GoogleRateLimited(
            "google asked us to slow down",
            retry_after_seconds=_retry_after(response),
        )
    raise GoogleOAuthError(f"google search console returned {status}")


def _retry_after(response: httpx.Response) -> int | None:
    """The Retry-After header, if it is a plain number of seconds."""

    raw = response.headers.get("retry-after", "").strip()
    if not raw.isdigit():
        return None
    return min(int(raw), 3600)


def _json_object(response: httpx.Response, *, what: str) -> dict[str, Any]:
    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise GoogleResponseInvalid(f"google returned a non-JSON {what} response") from exc
    if not isinstance(payload, dict):
        raise GoogleResponseInvalid(f"google returned an unexpected {what} response")
    return payload


def _number(value: Any) -> float | None:
    """A Search Analytics metric, or None if it is not one.

    ``bool`` is excluded deliberately: it is an ``int`` in Python, and letting
    ``True`` become ``1.0`` clicks is the kind of coercion that turns a shape
    change into a plausible-looking statistic.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _search_analytics_row(row: Any, *, expected_keys: int) -> SearchAnalyticsRow | None:
    if not isinstance(row, dict):
        return None

    raw_keys = row.get("keys", [])
    if expected_keys:
        if not isinstance(raw_keys, list) or len(raw_keys) != expected_keys:
            return None
        if not all(isinstance(key, str) for key in raw_keys):
            return None
        keys = tuple(str(key) for key in raw_keys)
    else:
        keys = ()

    clicks = _number(row.get("clicks"))
    impressions = _number(row.get("impressions"))
    ctr = _number(row.get("ctr"))
    position = _number(row.get("position"))
    if clicks is None or impressions is None or ctr is None or position is None:
        return None

    return SearchAnalyticsRow(
        keys=keys,
        clicks=clicks,
        impressions=impressions,
        ctr=ctr,
        position=position,
    )


def _identity_from_claims(claims: dict[str, Any]) -> GoogleIdentity:
    """The checks ``verify_oauth2_token`` does not do, plus the identity itself.

    The library validates signature, audience and expiry. Issuer it checks
    loosely enough to be worth restating. The nonce it does not know about at
    all — it is required here and returned for the service layer to match
    against the attempt, which is the difference between "this token is genuine"
    and "this token was minted for this attempt".
    """

    if claims.get("iss") not in _ACCEPTED_ISSUERS:
        raise GoogleIdentityError("google id token has an unexpected issuer")

    token_nonce = claims.get("nonce")
    if not isinstance(token_nonce, str) or not token_nonce:
        raise GoogleIdentityError("google id token carried no nonce")

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise GoogleIdentityError("google id token carried no subject")

    email = claims.get("email")
    if not isinstance(email, str) or not email:
        raise GoogleIdentityError("google id token carried no email")

    # An unverified address is one the account holder never proved they own, so
    # it must not become the label a user recognises their connection by.
    if claims.get("email_verified") is not True:
        raise GoogleIdentityError("google id token email is not verified")

    return GoogleIdentity(subject=subject, email=email, nonce=token_nonce)
