"""The GSC switch and the four values it makes mandatory.

The whole point of validating here rather than at the first click is that an
incomplete opt-in should fail a deploy, not a user's afternoon. So these tests
assert on both directions: off must stay boot-safe with nothing configured, and
on must refuse to boot with anything missing.

Every field is passed explicitly rather than through the environment, so a
developer's own ``backend/.env`` cannot make a "missing config" test pass.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import GOOGLE_OAUTH_SCOPES, Settings
from app.services.token_crypto import generate_encryption_key

REDIRECT_URI = "http://localhost:8141/api/v1/integrations/google-search-console/callback"


def _complete(**overrides) -> dict[str, object]:
    fields: dict[str, object] = {
        "gsc_enabled": True,
        "google_oauth_client_id": "123.apps.googleusercontent.com",
        "google_oauth_client_secret": "test-client-secret",
        "google_oauth_redirect_uri": REDIRECT_URI,
        "token_encryption_key": generate_encryption_key(),
    }
    fields.update(overrides)
    return fields


def test_defaults_leave_the_feature_off_and_unconfigured():
    settings = Settings()

    assert settings.gsc_enabled is False
    assert settings.google_oauth_client_id == ""
    assert settings.google_oauth_client_secret.get_secret_value() == ""
    assert settings.google_oauth_redirect_uri == ""
    assert settings.token_encryption_key.get_secret_value() == ""
    assert settings.gsc_oauth_state_ttl_seconds == 600


def test_blank_google_config_is_accepted_while_the_feature_is_off():
    """Zero-configuration boot must survive this card, as config.py promises."""

    settings = Settings(
        gsc_enabled=False,
        google_oauth_client_id="",
        google_oauth_client_secret="",
        google_oauth_redirect_uri="",
        token_encryption_key="",
    )

    assert settings.gsc_enabled is False


def test_complete_config_is_accepted_when_enabled():
    settings = Settings(**_complete())

    assert settings.gsc_enabled is True
    assert settings.google_oauth_redirect_uri == REDIRECT_URI


@pytest.mark.parametrize(
    ("field", "reported"),
    [
        ("google_oauth_client_id", "GOOGLE_OAUTH_CLIENT_ID"),
        ("google_oauth_client_secret", "GOOGLE_OAUTH_CLIENT_SECRET"),
        ("google_oauth_redirect_uri", "GOOGLE_OAUTH_REDIRECT_URI"),
        ("token_encryption_key", "TOKEN_ENCRYPTION_KEY"),
    ],
)
def test_enabling_without_each_required_value_fails_closed(field, reported):
    with pytest.raises(ValidationError) as caught:
        Settings(**_complete(**{field: ""}))

    assert reported in str(caught.value)


def test_whitespace_is_not_configuration():
    with pytest.raises(ValidationError):
        Settings(**_complete(google_oauth_client_id="   "))


def test_the_failure_names_every_missing_value_at_once():
    """One boot, one complete list — not four deploys to find four blanks."""

    with pytest.raises(ValidationError) as caught:
        Settings(gsc_enabled=True)

    message = str(caught.value)
    for name in (
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REDIRECT_URI",
        "TOKEN_ENCRYPTION_KEY",
    ):
        assert name in message


def test_the_failure_does_not_quote_configured_secrets_back():
    with pytest.raises(ValidationError) as caught:
        Settings(**_complete(google_oauth_client_id="", google_oauth_client_secret="hunter2-shh"))

    assert "hunter2-shh" not in str(caught.value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("example.com/callback", id="no-scheme"),
        pytest.param("ftp://example.com/callback", id="wrong-scheme"),
        pytest.param("https:///callback", id="no-host"),
        pytest.param("https://example.com/callback#fragment", id="fragment-google-rejects"),
    ],
)
def test_a_redirect_uri_google_would_reject_is_refused(value):
    with pytest.raises(ValidationError):
        Settings(google_oauth_redirect_uri=value)


def test_a_bad_redirect_uri_is_caught_even_while_the_feature_is_off():
    """A typo should surface at the boot that introduced it, not months later."""

    with pytest.raises(ValidationError):
        Settings(gsc_enabled=False, google_oauth_redirect_uri="not-a-url")


def test_the_dev_redirect_uri_points_at_the_api_port_not_the_web_port():
    """8141 is YANKI_API_PORT; 8140 is the web app. Google returns to the API."""

    settings = Settings(google_oauth_redirect_uri=REDIRECT_URI)

    assert settings.google_oauth_redirect_uri.startswith("http://localhost:8141/")
    assert settings.public_base_url == "http://localhost:8140"


def test_the_state_ttl_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(gsc_oauth_state_ttl_seconds=0)


def test_the_requested_scopes_are_exactly_the_three_agreed():
    """Pinned, because widening this is the one change worth noticing in review.

    ``openid``/``email`` exist to get a verified ID token — the only trustworthy
    source of which Google account authorized a connection. Search Console
    access is read-only.
    """

    assert GOOGLE_OAUTH_SCOPES == (
        "openid",
        "email",
        "https://www.googleapis.com/auth/webmasters.readonly",
    )


def test_no_write_capable_search_console_scope_is_requested():
    """``webmasters`` without ``.readonly`` can delete a property. Never ask."""

    assert "https://www.googleapis.com/auth/webmasters" not in GOOGLE_OAUTH_SCOPES


def test_the_scope_list_is_not_operator_configurable():
    """A scope list reachable from .env is a scope list nobody reviews."""

    assert not hasattr(Settings(), "google_oauth_scopes")
