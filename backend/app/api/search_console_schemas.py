"""Request/response models for the Search Console surface.

What these models leave out is as deliberate as what they carry. No access
token, no refresh token, no ciphertext, no client secret, no PKCE verifier, no
nonce, no state, and nothing from a Google error body. The schema is the last
place a credential can leak by accident, because a field added here is a field
serialized to every caller forever.

``scopes`` is the one place a stored string is reshaped for the client: the
column holds the canonical space-delimited form, and a list is what a UI wants.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

PropertyType = Literal["domain", "url_prefix"]

ProjectConnectionStatus = Literal[
    # No Google account is connected to this organization at all.
    "no_connection",
    # An account is connected, but this project has not chosen a property.
    "no_property_selected",
    # A property is linked and the connection behind it looks healthy.
    "connected",
    # A property is linked but its connection needs the user to reconnect.
    "reauth_required",
]


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


class SearchConsoleConnectionOut(BaseModel):
    """One connected Google account, as it is safe to describe it."""

    id: uuid.UUID
    google_account_email: str = Field(
        ...,
        description="From the verified ID token. Shown so several accounts can be told apart.",
    )
    status: str = Field(..., description="'active' or 'reauth_required'.")
    scopes: list[str] = Field(
        ...,
        description="Scopes Google actually granted, not the ones requested.",
    )
    created_at: datetime
    updated_at: datetime
    selected_for_project: bool = Field(
        ...,
        description="Whether this project's Search Console property comes from this account.",
    )
    selected_site_url: str | None = Field(
        None,
        description="The linked property, when this account is the selected one.",
    )


class SearchConsoleConnectionsOut(BaseModel):
    """Every Google account in the organization, plus this project's standing."""

    project_status: ProjectConnectionStatus
    connections: list[SearchConsoleConnectionOut]


class SearchConsolePropertyOut(BaseModel):
    """One property the connected account can reach."""

    site_url: str = Field(
        ...,
        description=(
            "Google's own identifier, verbatim — 'sc-domain:example.com' or "
            "'https://example.com/'. It is the argument every later API call needs."
        ),
    )
    permission_level: str = Field(..., description="Google's permission string, unmapped.")
    property_type: PropertyType
    matches_project_domain: bool = Field(
        ...,
        description=(
            "Exact host match against the project's domain. A suggestion only: "
            "nothing is ever linked automatically, and a non-matching property "
            "may still be chosen."
        ),
    )
    currently_selected: bool


class SearchConsolePropertiesOut(BaseModel):
    """The pick-list, ordered suggested-first then selected then alphabetical."""

    google_connection_id: uuid.UUID
    google_account_email: str
    properties: list[SearchConsolePropertyOut]


class SearchConsolePropertyLinkRequest(BaseModel):
    """Which property to point this project at.

    ``site_url`` is checked against the live list from Google before anything is
    stored — it names a choice, it does not assert one.
    """

    google_connection_id: uuid.UUID
    site_url: str = Field(..., min_length=1, max_length=2048)


class SearchConsolePropertyLinkOut(BaseModel):
    """The link as it now stands."""

    google_connection_id: uuid.UUID
    google_account_email: str
    site_url: str
    property_type: PropertyType
    permission_level: str = Field(
        ...,
        description="Taken from Google's list at link time, never from the request.",
    )
    connected_at: datetime
    updated_at: datetime


class SearchConsoleMetricsOut(BaseModel):
    """Property-wide totals for the window.

    ``ctr`` and ``position`` are null rather than 0 when there were no
    impressions: an average over nothing is not zero, and a position of 0 would
    read as "ranked above the first result".
    """

    clicks: float
    impressions: float
    ctr: float | None
    position: float | None


class SearchConsoleRowOut(BaseModel):
    """One query or one page."""

    key: str
    clicks: float
    impressions: float
    ctr: float
    position: float


class SearchConsolePerformanceOut(BaseModel):
    """Live Search Console performance. Nothing here is cached server-side."""

    site_url: str
    start_date: date
    end_date: date
    data_state: Literal["ok", "no_data"]
    summary: SearchConsoleMetricsOut
    top_queries: list[SearchConsoleRowOut]
    top_pages: list[SearchConsoleRowOut]
