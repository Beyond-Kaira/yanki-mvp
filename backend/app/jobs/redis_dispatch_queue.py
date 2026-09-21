"""Redis job dispatch queue — pointers only, with Postgres fallback.

When ``Settings.redis_url`` is set, enqueue pushes job ids to Redis lists and
workers pop them with BRPOP. Run state (status, results, artifacts) stays in
Postgres. When Redis is disabled, ``NullDispatchQueue`` is a no-op and existing
``claim_next*`` polling handles dispatch.
"""

from __future__ import annotations

from typing import Protocol

from app.config import Settings

QUEUE_ANALYSIS = "queue:analysis"
QUEUE_MODULE = "queue:module"
QUEUE_SITE_AUDIT = "queue:site_audit"

DEFAULT_POP_TIMEOUT_SECONDS = 1


class DispatchQueue(Protocol):
    def push(self, queue: str, job_id: str) -> None: ...

    def pop(self, queue: str, *, timeout_seconds: float = DEFAULT_POP_TIMEOUT_SECONDS) -> str | None: ...


class NullDispatchQueue:
    """Fallback when Redis is off — dispatch stays on Postgres ``claim_next``."""

    def push(self, queue: str, job_id: str) -> None:
        return None

    def pop(self, queue: str, *, timeout_seconds: float = DEFAULT_POP_TIMEOUT_SECONDS) -> str | None:
        return None


class RedisDispatchQueue:
    """Redis list queue: LPUSH to enqueue, BRPOP to dequeue."""

    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def push(self, queue: str, job_id: str) -> None:
        self._client.lpush(queue, job_id)

    def pop(self, queue: str, *, timeout_seconds: float = DEFAULT_POP_TIMEOUT_SECONDS) -> str | None:
        timeout = max(0, int(timeout_seconds))
        result = self._client.brpop(queue, timeout=timeout)
        if result is None:
            return None
        _key, job_id = result
        return job_id


def get_dispatch_queue(settings: Settings) -> DispatchQueue:
    url = (settings.redis_url or "").strip()
    if url:
        return RedisDispatchQueue(url)
    return NullDispatchQueue()
