"""Redis job dispatch queue — pointers only, with Postgres fallback.

When ``Settings.redis_url`` is set, enqueue pushes job ids to Redis lists and
workers pop them with BRPOP. Run state (status, results, artifacts) stays in
Postgres. When Redis is disabled, ``PostgresFallbackDispatch`` is a no-op and
existing ``claim_next*`` polling handles dispatch.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from app.config import Settings

QUEUE_ANALYSIS = "queue:analysis"
QUEUE_MODULE = "queue:module"
QUEUE_SITE_AUDIT = "queue:site_audit"

DEFAULT_POP_TIMEOUT_SECONDS = 1


class JobDispatchBackend(Protocol):
    def push(self, queue: str, job_id: str) -> None: ...

    def pop(
        self, queue: str, *, timeout_seconds: float = DEFAULT_POP_TIMEOUT_SECONDS
    ) -> str | None: ...

    def try_pop(self, queue: str) -> str | None: ...


class PostgresFallbackDispatch:
    """Fallback when Redis is off — dispatch stays on Postgres ``claim_next``."""

    def push(self, queue: str, job_id: str) -> None:
        return None

    def pop(
        self, queue: str, *, timeout_seconds: float = DEFAULT_POP_TIMEOUT_SECONDS
    ) -> str | None:
        return None

    def try_pop(self, queue: str) -> str | None:
        return None


class RedisListDispatch:
    """Redis list queue: LPUSH to enqueue, BRPOP/RPOP to dequeue."""

    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def push(self, queue: str, job_id: str) -> None:
        self._client.lpush(queue, job_id)

    def pop(
        self, queue: str, *, timeout_seconds: float = DEFAULT_POP_TIMEOUT_SECONDS
    ) -> str | None:
        timeout = max(0, int(timeout_seconds))
        result = self._client.brpop(queue, timeout=timeout)
        if result is None:
            return None
        _key, job_id = result
        return job_id

    def try_pop(self, queue: str) -> str | None:
        return self._client.rpop(queue)


def connect_from_settings(settings: Settings) -> JobDispatchBackend:
    """Return the configured job-id dispatch backend for this process."""

    url = (settings.redis_url or "").strip()
    if url:
        return RedisListDispatch(url)
    return PostgresFallbackDispatch()


def notify_analysis_enqueued(analysis_id: uuid.UUID, settings: Settings) -> None:
    """Push an analysis id onto the Redis dispatch list (no-op when Redis is off)."""

    connect_from_settings(settings).push(QUEUE_ANALYSIS, str(analysis_id))


def redis_is_enabled(settings: Settings) -> bool:
    return bool((settings.redis_url or "").strip())


def queue_depth(settings: Settings, queue: str) -> int | None:
    """Return the Redis list length, or ``None`` when dispatch uses Postgres fallback."""

    backend = connect_from_settings(settings)
    if not isinstance(backend, RedisListDispatch):
        return None
    return int(backend._client.llen(queue) or 0)


def ping_redis(settings: Settings) -> bool:
    """Return whether Redis answers PING when dispatch is configured."""

    backend = connect_from_settings(settings)
    if not isinstance(backend, RedisListDispatch):
        return False
    return bool(backend._client.ping())
