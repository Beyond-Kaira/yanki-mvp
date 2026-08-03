"""A tiny search backend SearXNG can be pointed at, so CI is deterministic.

The problem this solves: the public engines SearXNG normally federates (Google,
Brave, DuckDuckGo, Startpage) refuse CI runners outright — measured on a live
instance, one ordinary query came back with *all four* suspended or CAPTCHA'd.
An integration test asserting "we found results" against those would be a coin
flip, and a flaky gate is a gate people learn to ignore.

So the CI instance federates exactly one engine: this server, over
``json_engine``. Results are fixed, so the assertions can be exact — and, more
usefully, the failure modes are *summonable*, which is what lets the test prove
the honesty rule against real SearXNG rather than against a mock of it:

* ``__empty__`` in the query -> a healthy instance with nothing to show. Must
  read as a genuine miss.
* ``__boom__`` in the query  -> the engine errors, so SearXNG reports it under
  ``unresponsive_engines``. Must read as "not measured", never as a miss.

Standard library only, no dependencies: it is run with whatever ``python3`` is
already in the job.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# The brand the integration test looks for. Deliberately not a real company.
BRAND = "Zendrix Robotics"
BRAND_URL = "https://zendrix-robotics.example/"

FIXTURES: dict[str, list[dict[str, str]]] = {
    "best warehouse robots": [
        {
            "title": f"{BRAND} — warehouse automation",
            "url": BRAND_URL,
            "content": f"{BRAND} builds autonomous warehouse robots.",
        },
        {
            "title": "Globex Automation",
            "url": "https://globex.example/robots",
            "content": "Globex also sells warehouse robots.",
        },
    ],
}

# Anything unrecognised: results that exist but never name the brand, so a
# "not found" assertion is about detection rather than about an empty page.
DEFAULT: list[dict[str, str]] = [
    {
        "title": "Globex Automation",
        "url": "https://globex.example/robots",
        "content": "Globex sells warehouse robots.",
    },
    {
        "title": "Initech Handling",
        "url": "https://initech.example/",
        "content": "Initech makes conveyors.",
    },
]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 (http.server's required spelling)
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._send(200, b"ok", "text/plain")
            return

        query = (parse_qs(parsed.query).get("q", [""])[0] or "").strip().lower()
        if "__boom__" in query:
            self._send(500, b'{"error": "summoned failure"}', "application/json")
            return

        results = [] if "__empty__" in query else FIXTURES.get(query, DEFAULT)
        body = json.dumps({"query": query, "results": results}).encode("utf-8")
        self._send(200, body, "application/json")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        """Silence per-request logging; the job log is for the test, not this."""


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
