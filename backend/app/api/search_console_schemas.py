"""Request/response models for the Search Console connection surface.

There is exactly one response body in this slice, and what it leaves out is the
design: no access token, no refresh token, no client secret, no PKCE verifier,
no nonce, no state. The browser needs one thing to continue the flow — where to
go — and every additional field would be a credential handed to JavaScript for
no reason.

The callback returns a redirect, not a body, so it has no schema here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchConsoleConnectStartOut(BaseModel):
    """Where to send the browser to authorize Yanki against Google."""

    authorization_url: str = Field(
        ...,
        description=(
            "Absolute Google OAuth 2.0 authorization URL. The frontend performs a "
            "full-page navigation to it; it carries no client secret and is "
            "single-use, because the state inside it is."
        ),
    )
