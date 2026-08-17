"""Verification of Google / Apple identity tokens.

The browser performs the sign-in and hands us the provider's ``id_token``; this
module decides whether to believe it. Nothing here talks to the provider on the
user's behalf, so there is no client secret, no redirect state and no callback —
the token is self-contained and its signature is the whole proof.

Two checks carry the security of the feature. The signature must verify against
the provider's published keys, and the ``aud`` claim must name *our* client id:
a token is minted for one application, and one that names another application is
somebody else's proof of somebody else's session.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.config import Settings

PROVIDERS = ("google", "apple")


@dataclass(frozen=True, slots=True)
class _ProviderSpec:
    issuers: tuple[str, ...]
    jwks_uri: str


_SPECS: dict[str, _ProviderSpec] = {
    "google": _ProviderSpec(
        # Google signs with either spelling of its issuer and both are valid.
        issuers=("https://accounts.google.com", "accounts.google.com"),
        jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
    ),
    "apple": _ProviderSpec(
        issuers=("https://appleid.apple.com",),
        jwks_uri="https://appleid.apple.com/auth/keys",
    ),
}


@dataclass(frozen=True, slots=True)
class OAuthIdentity:
    """Who the provider says the caller is."""

    provider: str
    subject: str
    email: str


class OAuthConfigurationError(RuntimeError):
    """Raised when a provider has no client id configured."""


class OAuthTokenError(ValueError):
    """Raised when an identity token cannot be trusted."""


@lru_cache(maxsize=len(PROVIDERS))
def _jwk_client(jwks_uri: str) -> PyJWKClient:
    """One key client per provider, kept so its key cache survives requests.

    Fetching the key set on every sign-in would put the provider's availability
    in the path of every login. The client refreshes on an unknown key id, which
    is exactly when a provider has rotated.
    """

    return PyJWKClient(jwks_uri, cache_keys=True)


def verify_id_token(
    *,
    provider: str,
    id_token: str,
    settings: Settings,
) -> OAuthIdentity:
    """Validate a provider ``id_token`` and return the identity it asserts."""

    spec = _SPECS.get(provider)
    if spec is None:
        raise OAuthTokenError("unsupported provider")

    client_id = (
        settings.google_client_id if provider == "google" else settings.apple_client_id
    ).strip()
    if not client_id:
        raise OAuthConfigurationError(f"{provider} client id is not configured")

    try:
        signing_key = _jwk_client(spec.jwks_uri).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=list(spec.issuers),
            options={"require": ["sub", "aud", "iss", "exp"]},
            leeway=settings.jwt_clock_skew_seconds,
        )
    except PyJWKClientError as exc:
        # The provider's key set was unreachable or unusable. Not the caller's
        # fault, so it must not read as a rejected token.
        raise OAuthConfigurationError(f"{provider} signing keys unavailable") from exc
    except InvalidTokenError as exc:
        raise OAuthTokenError("invalid identity token") from exc

    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise OAuthTokenError("identity token carries no email")

    # Apple sends this as the string "true"; Google as a boolean. An address the
    # provider has not verified is an address anyone could have typed, and we
    # match accounts on it — so an unverified one is an account takeover.
    if claims.get("email_verified") not in (True, "true"):
        raise OAuthTokenError("identity token email is not verified")

    return OAuthIdentity(provider=provider, subject=str(claims["sub"]), email=email)
