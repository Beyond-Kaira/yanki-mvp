"""Selecting a Google OAuth provider — one function, mirroring the other seams.

``None`` is a first-class answer: the module is off. Callers turn that into the
same 404 the whole router already returns, rather than constructing a client
against blank credentials and discovering the problem at Google.

Unlike ``app/backlink/registry.py``, **DRY_RUN does not force the mock here.**
That deviation is deliberate and it is the opposite trade for the opposite
reason: DRY_RUN exists to stop a test run from spending money at a metered
vendor, and OAuth spends nothing. What it would cost instead is the ability to
connect a real Google account in a development stack, which is exactly the thing
an operator needs to try before this ships. The guarantee that the test suite
never reaches Google comes from the tests injecting the mock provider directly,
which is stronger than a settings flag they could forget to set.
"""

from __future__ import annotations

from app.config import Settings
from app.gsc.base import GoogleOAuthProvider
from app.gsc.google import GoogleOAuthClient


def get_google_oauth_provider(settings: Settings) -> GoogleOAuthProvider | None:
    """The configured Google client, or None while the module is switched off."""

    if not settings.gsc_enabled:
        return None

    # Settings validation already refused to boot with GSC_ENABLED and blank
    # credentials, so reaching here means the client id, secret and redirect URI
    # are all present.
    return GoogleOAuthClient(settings)
