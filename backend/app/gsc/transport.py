"""An httpx-backed transport for ``google-auth``.

``google.oauth2.id_token.verify_oauth2_token`` needs a callable conforming to
``google.auth.transport.Request`` so it can fetch Google's signing certificates.
The library ships one, but it is built on ``requests`` — a second HTTP client in
a codebase that uses ``httpx`` everywhere else, pulled in for exactly one GET
against a public, unauthenticated URL.

So this adapts httpx to that interface instead. It is about twenty lines, and it
is the reason ``google-auth`` appears in ``pyproject.toml`` without the
``[requests]`` extra.

The one hazard in writing a transport by hand is that it only ever runs in
production — every test that mocks the provider skips straight past it. So it is
tested directly against ``respx`` in ``tests/test_gsc_transport.py`` rather than
being trusted because the code above it passes.
"""

from __future__ import annotations

from typing import Any

import httpx
from google.auth.transport import Request as GoogleAuthRequest
from google.auth.transport import Response as GoogleAuthResponse

# Certificate fetches are a hard dependency of verifying an identity, so they get
# a bounded wait rather than google-auth's unbounded default.
DEFAULT_TIMEOUT_SECONDS = 10.0


class _Response(GoogleAuthResponse):
    """google-auth reads exactly these three members.

    They are declared ``@abc.abstractproperty`` on the base class, so plain
    instance attributes do not satisfy it — the class stays abstract and
    instantiating it raises. Found by ``tests/test_gsc_transport.py``, which is
    the entire reason that file exists: every other test injects the mock
    provider and would never have executed this line before production did.
    """

    def __init__(self, response: httpx.Response) -> None:
        self._status = response.status_code
        self._headers = dict(response.headers)
        self._data = response.content

    @property
    def status(self) -> int:
        return self._status

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    @property
    def data(self) -> bytes:
        return self._data


class HttpxRequest(GoogleAuthRequest):
    """``google.auth.transport.Request``, implemented over httpx."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def __call__(  # noqa: D102 - the interface's own docstring applies
        self,
        url: str,
        method: str = "GET",
        body: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> GoogleAuthResponse:
        with httpx.Client(timeout=timeout or self._timeout) as client:
            response = client.request(
                method,
                url,
                content=body,
                headers=headers,
            )
        return _Response(response)
