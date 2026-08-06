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
from urllib.parse import urlencode

import httpx
from google.auth.exceptions import GoogleAuthError as _LibraryAuthError
from google.oauth2 import id_token as google_id_token

from app.config import GOOGLE_OAUTH_SCOPES, Settings
from app.gsc.base import (
    GoogleIdentity,
    GoogleIdentityError,
    GoogleOAuthError,
    GoogleTokens,
)
from app.gsc.transport import HttpxRequest

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

# Google mints ID tokens under both spellings and treats them as equivalent.
_ACCEPTED_ISSUERS = ("accounts.google.com", "https://accounts.google.com")

_TOKEN_TIMEOUT_SECONDS = 15.0


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
