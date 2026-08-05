"""Ambient per-request identity for the audit trail.

The audit spine wants three things every event should carry — a request id, a
salted client-IP hash, and the user agent — and they are known in exactly one
place (the ASGI layer) and needed in a different one (whatever service happens
to mutate something). Threading them through every function signature between
those two points would mean every service grows an argument it does not use,
and the first developer to forget it produces an event that silently lacks the
fields an investigation needs.

So they ride a :class:`~contextvars.ContextVar`, set once by the middleware and
read by :func:`app.services.audit.emit` as a default. Three consequences worth
being explicit about:

* **Explicit beats ambient.** ``emit`` uses the context only for fields the
  caller did not pass. A worker that knows its own request id still wins.
* **``ContextVar`` is the right primitive, not a global.** It is per-task, so
  concurrent requests in the same event loop cannot read each other's ids, and
  it survives ``await`` — which a thread-local would not, since Starlette may
  resume a coroutine on a different worker thread.
* **Outside a request the context is empty**, and every field degrades to
  ``None``. The worker and the CLI emit events with no request id, which is the
  truth about them rather than a gap to paper over.

The request id is also echoed as ``X-Request-Id`` on the response, so a user
reporting a problem can quote the exact string that appears in the audit row.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.config import get_settings
from app.services.rate_limit import client_ip, hash_ip

REQUEST_ID_HEADER = "X-Request-Id"

# An inbound request id is a convenience for correlating with an upstream proxy,
# not a trusted value: it lands in a log and in an audit row, so it is bounded
# and character-restricted before it is believed. Anything else is replaced with
# a generated id rather than rejected — a malformed header is not worth failing
# a request over.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(frozen=True)
class RequestInfo:
    """What the HTTP layer knows that the audit trail wants."""

    request_id: str
    ip_hash: str | None = None
    user_agent: str | None = None


_current: ContextVar[RequestInfo | None] = ContextVar("yanki_request_info", default=None)


def current_request_info() -> RequestInfo | None:
    """The current request's audit metadata, or ``None`` outside a request."""

    return _current.get()


def set_request_info(info: RequestInfo | None):
    """Install request metadata. Returns the token needed to reset it."""

    return _current.set(info)


def reset_request_info(token) -> None:
    """Restore whatever was installed before :func:`set_request_info`."""

    _current.reset(token)


def new_request_id() -> str:
    """A fresh request id — a bare hex uuid, compact enough to quote by hand."""

    return uuid.uuid4().hex


def request_info_from(request: Request) -> RequestInfo:
    """Build the context for one inbound request.

    The IP is hashed with the **same salt** the rate limiter uses. There is
    deliberately no second salt: two salts would make the same visitor look like
    two different people depending on which subsystem recorded them, which
    defeats the reason for hashing consistently in the first place.
    """

    inbound = request.headers.get(REQUEST_ID_HEADER)
    request_id = inbound if inbound and _SAFE_REQUEST_ID.match(inbound) else new_request_id()

    ip = client_ip(request)
    settings = get_settings()
    user_agent = request.headers.get("user-agent")

    return RequestInfo(
        request_id=request_id,
        ip_hash=hash_ip(ip, settings.ip_hash_salt) if ip else None,
        user_agent=user_agent[:500] if user_agent else None,
    )


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Set the request context for the lifetime of one request, then clear it.

    Resetting in a ``finally`` matters more than it looks: without it a context
    var set on a pooled task can outlive its request, and the next event emitted
    from that task would be attributed to the previous caller's IP.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        info = request_info_from(request)
        token = set_request_info(info)
        try:
            response = await call_next(request)
        finally:
            reset_request_info(token)
        response.headers[REQUEST_ID_HEADER] = info.request_id
        return response
