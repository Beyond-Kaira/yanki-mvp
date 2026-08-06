"""A deterministic Google, for tests and DRY_RUN.

Mirrors ``app/backlink/mock.py``: a pure function of its inputs, no clock, no
network, no randomness. The whole OAuth flow — state, PKCE, nonce, the exchange,
identity verification — runs end to end against this, so the tests exercise the
service layer's real logic rather than a stub of it.

It enforces the checks the real adapter enforces (nonce match, subject and
verified email present) so a test that would pass here and fail against Google
is hard to write. What it does not do is verify a signature: there is no key.
That is the one thing ``tests/test_gsc_transport.py`` and the real adapter's own
error mapping have to cover instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlencode

from app.config import GOOGLE_OAUTH_SCOPES
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

MOCK_AUTHORIZATION_ENDPOINT = "https://accounts.google.test/o/oauth2/v2/auth"

# A default estate covering both property kinds plus the entries the service is
# expected to drop, so the ordinary test path already exercises the filtering.
DEFAULT_PROPERTIES: tuple[GoogleProperty, ...] = (
    GoogleProperty(site_url="https://shop.acme.test/", permission_level="siteFullUser"),
    GoogleProperty(site_url="sc-domain:acme.test", permission_level="siteOwner"),
    GoogleProperty(site_url="https://www.acme.test/", permission_level="siteOwner"),
    GoogleProperty(site_url="https://unverified.test/", permission_level="siteUnverifiedUser"),
)


@dataclass
class MockGoogleOAuthProvider:
    """A configurable stand-in for Google.

    Every knob exists because a test needs to drive the flow into one of the
    branches the service layer must handle: a user who declines to share a
    refresh token, an identity Google will not vouch for, an outage.
    """

    name: str = "mock"
    client_id: str = "mock-client-id.apps.googleusercontent.com"
    redirect_uri: str = "http://localhost:8141/api/v1/integrations/google-search-console/callback"

    subject: str = "mock-google-sub"
    email: str = "owner@example.test"
    email_verified: bool = True
    refresh_token: str | None = "mock-refresh-token"
    access_token: str = "mock-access-token"
    granted_scope: str | None = None

    # Failure switches.
    fail_exchange: bool = False
    fail_identity: bool = False
    # The nonce the ID token will claim. None means "echo the one the
    # authorization request carried", which is the honest case; setting it
    # simulates a token minted for some other attempt.
    id_token_nonce: str | None = None

    # Search Console.
    properties: tuple[GoogleProperty, ...] = DEFAULT_PROPERTIES
    refreshed_access_token: str = "mock-fresh-access-token"
    # Rows returned per query shape, keyed by the dimensions requested. ()
    # is the property-wide summary. An empty tuple for a key models a property
    # with no data in the window, which is a different thing from a failure.
    analytics_rows: dict[tuple[str, ...], tuple[SearchAnalyticsRow, ...]] | None = None

    # Failure switches for everything past the connect flow.
    revoke_refresh: bool = False
    fail_list_properties: bool = False
    forbid_property: bool = False
    rate_limited: bool = False
    malformed_analytics: bool = False

    # Populated on use, so tests can assert what was actually sent.
    exchanges: list[dict[str, str]] = field(default_factory=list)
    issued_nonces: list[str] = field(default_factory=list)
    refreshed_tokens: list[str] = field(default_factory=list)
    analytics_queries: list[dict[str, object]] = field(default_factory=list)

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        # Remembered so the exchange can echo it back inside the ID token, the
        # way Google does — without this the mock could never fail a nonce check
        # honestly.
        self.issued_nonces.append(nonce)

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_OAUTH_SCOPES),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent select_account",
        }
        return f"{MOCK_AUTHORIZATION_ENDPOINT}?{urlencode(params)}"

    def exchange_code(self, *, code: str, code_verifier: str) -> GoogleTokens:
        if self.fail_exchange:
            raise GoogleOAuthError("mock google refused the code")

        # Recorded rather than checked: the assertion that the PKCE verifier
        # from the state row reached the exchange belongs in the test, not here.
        self.exchanges.append({"code": code, "code_verifier": code_verifier})

        return GoogleTokens(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            id_token="mock-id-token",
            scope=(
                self.granted_scope
                if self.granted_scope is not None
                else " ".join(GOOGLE_OAUTH_SCOPES)
            ),
            expires_in=3599,
        )

    def verify_identity(self, *, id_token: str) -> GoogleIdentity:
        if self.fail_identity:
            raise GoogleIdentityError("mock google would not verify this identity")

        if self.id_token_nonce is not None:
            claimed_nonce = self.id_token_nonce
        elif self.issued_nonces:
            claimed_nonce = self.issued_nonces[-1]
        else:
            raise GoogleIdentityError("google id token carried no nonce")

        if not claimed_nonce:
            raise GoogleIdentityError("google id token carried no nonce")
        if not self.subject:
            raise GoogleIdentityError("google id token carried no subject")
        if not self.email:
            raise GoogleIdentityError("google id token carried no email")
        if not self.email_verified:
            raise GoogleIdentityError("google id token email is not verified")

        return GoogleIdentity(subject=self.subject, email=self.email, nonce=claimed_nonce)

    # ----------------------------------------------------------------------
    # Search Console
    # ----------------------------------------------------------------------

    def refresh_access_token(self, *, refresh_token: str) -> GoogleAccessToken:
        if self.revoke_refresh:
            raise GoogleAuthorizationRevoked("mock google refused the stored refresh token")

        # Recorded so a test can prove the *decrypted* token reached the
        # provider, which is the only observable evidence that the ciphertext
        # round-trip actually happened.
        self.refreshed_tokens.append(refresh_token)
        return GoogleAccessToken(access_token=self.refreshed_access_token, expires_in=3599)

    def list_properties(self, *, access_token: str) -> tuple[GoogleProperty, ...]:
        if self.rate_limited:
            raise GoogleRateLimited("mock google asked us to slow down", retry_after_seconds=30)
        if self.fail_list_properties:
            raise GoogleOAuthError("mock google search console was unreachable")
        return self.properties

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
        if self.rate_limited:
            raise GoogleRateLimited("mock google asked us to slow down", retry_after_seconds=30)
        if self.forbid_property:
            raise GoogleAccessForbidden("mock google refused access to this property")
        if self.malformed_analytics:
            raise GoogleResponseInvalid("mock google returned an unreadable body")

        self.analytics_queries.append(
            {
                "site_url": site_url,
                "start_date": start_date,
                "end_date": end_date,
                "dimensions": dimensions,
                "row_limit": row_limit,
            }
        )

        if self.analytics_rows is None:
            return ()
        return self.analytics_rows.get(dimensions, ())
