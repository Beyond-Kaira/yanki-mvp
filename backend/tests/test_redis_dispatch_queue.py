"""Redis dispatch queue — Redis and Postgres-fallback paths."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.jobs.redis_dispatch_queue import (
    QUEUE_ANALYSIS,
    NullDispatchQueue,
    RedisDispatchQueue,
    get_dispatch_queue,
)


def test_null_dispatch_queue_push_pop_are_noops():
    queue = NullDispatchQueue()
    queue.push(QUEUE_ANALYSIS, "job-1")
    assert queue.pop(QUEUE_ANALYSIS) is None


def test_get_dispatch_queue_returns_null_when_redis_url_unset(settings):
    queue = get_dispatch_queue(settings)
    assert isinstance(queue, NullDispatchQueue)


def test_get_dispatch_queue_returns_redis_when_url_set():
    queue = get_dispatch_queue(Settings(redis_url="redis://localhost:6379/0"))
    assert isinstance(queue, RedisDispatchQueue)


@pytest.fixture(scope="module")
def redis_queue():
    try:
        queue = RedisDispatchQueue("redis://127.0.0.1:6379/15")
        queue._client.ping()
    except Exception as exc:
        pytest.skip(f"local redis not available: {exc}")
    queue._client.flushdb()
    yield queue
    queue._client.flushdb()


def test_redis_dispatch_queue_push_pop_fifo(redis_queue):
    redis_queue.push(QUEUE_ANALYSIS, "first")
    redis_queue.push(QUEUE_ANALYSIS, "second")
    assert redis_queue.pop(QUEUE_ANALYSIS, timeout_seconds=1) == "first"
    assert redis_queue.pop(QUEUE_ANALYSIS, timeout_seconds=1) == "second"
    assert redis_queue.pop(QUEUE_ANALYSIS, timeout_seconds=0) is None
