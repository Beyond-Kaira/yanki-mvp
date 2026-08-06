"""The interface the Google OAuth provider implements.

Modelled on ``app/backlink/base.py``: a Protocol plus small frozen dataclasses,
no SQLAlchemy, no FastAPI, no settings lookups at call time. That is what lets
the whole OAuth flow be tested without a network, and what keeps the real
adapter swappable for a deterministic mock.

Two shapes carry the security of this module.

:class:`GoogleIdentity` exists so that *nothing downstream can invent an
identity*. It is only ever constructed from claims in a **verified** ID token.
The provider does the verifying; the service layer receives an identity it
cannot have built from a query parameter, because there is no other constructor
being called anywhere in the flow.

:class:`GoogleTokens` keeps ``refresh_token`` optional and ``access_token``
deliberately unused past this boundary. Google omits a refresh token on a
re-consent it considers redundant, and the service layer has to notice that
rather than write a connection that can never be refreshed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class GoogleOAuthError(Exception):
    """Google was unreachable, or answered in a way we will not act on.

    One exception for every provider-side failure — a network error, a non-200
    token response, an unparseable body. The service layer maps it to a single
    ``provider_error`` redirect, so Google's own error text never reaches a URL
    or a log line. Callers must not try to distinguish the cases: the
    distinctions are attacker-controlled.
    """


class GoogleIdentityError(GoogleOAuthError):
    """The ID token did not verify, or did not carry a usable identity.

    Raised for a bad signature, a wrong issuer or audience, an expired token, a
    nonce that does not match, a missing ``sub``/``email``, or an unverified
    email. Separate from its parent only so the service layer can redirect with
    ``invalid_identity`` rather than ``provider_error`` — the user can act on
    the first and not on the second.
    """


@dataclass(frozen=True, slots=True)
class GoogleTokens:
    """What the token endpoint returned for one authorization code.

    ``access_token`` is never persisted and never leaves the backend; it is here
    because the exchange returns it, not because anything stores it.
    """

    access_token: str
    # Absent when Google decides the grant already exists. A reconnect may
    # legitimately arrive without one; a first connection may not.
    refresh_token: str | None
    id_token: str
    # Space-delimited exactly as the token endpoint returned it. May be WIDER
    # than what was requested, because include_granted_scopes carries previously
    # granted scopes forward — which is why what was granted is recorded rather
    # than what was asked for.
    scope: str
    expires_in: int | None = None


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    """Who Google says authorized the connection. Verified claims only."""

    # The ID token `sub` claim: Google's stable, non-reassignable account id.
    subject: str
    # The `email` claim. Display only — an address can move between accounts,
    # which is exactly why `subject` is the identity.
    email: str
    # The `nonce` claim, carried out of the token rather than checked in here.
    # Only the *hash* of the nonce survives in the database, so the comparison
    # belongs to the service layer that can read the row — the provider's job
    # ends at proving this claim came from a genuine, unexpired, correctly
    # audienced token.
    nonce: str


@runtime_checkable
class GoogleOAuthProvider(Protocol):
    """One Google OAuth 2.0 / OIDC client behind an adapter."""

    name: str

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        """The URL to send the browser to. Carries no secret."""
        ...

    def exchange_code(self, *, code: str, code_verifier: str) -> GoogleTokens:
        """Trade an authorization code for tokens. Raises GoogleOAuthError."""
        ...

    def verify_identity(self, *, id_token: str) -> GoogleIdentity:
        """Verify signature, issuer, audience and expiry, then read the claims.

        Raises :class:`GoogleIdentityError` unless every check passes and the
        token carries a ``sub``, a verified ``email`` and a ``nonce``. Matching
        that nonce to the attempt is the service layer's job, because the
        database holds only its hash.
        """
        ...
