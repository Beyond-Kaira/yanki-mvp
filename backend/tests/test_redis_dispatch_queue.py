"""Redis dispatch queue — Redis and Postgres-fallback paths."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.jobs import redis_dispatch_queue


def test_postgres_fallback_dispatch_push_pop_are_noops():
    queue = redis_dispatch_queue.PostgresFallbackDispatch()
    queue.push(redis_dispatch_queue.QUEUE_ANALYSIS, "job-1")
    assert queue.try_pop(redis_dispatch_queue.QUEUE_ANALYSIS) is None


def test_connect_from_settings_returns_postgres_fallback_when_redis_url_unset(settings):
    queue = redis_dispatch_queue.connect_from_settings(settings)
    assert isinstance(queue, redis_dispatch_queue.PostgresFallbackDispatch)


def test_connect_from_settings_returns_redis_when_url_set():
    queue = redis_dispatch_queue.connect_from_settings(
        Settings(redis_url="redis://localhost:6379/0")
    )
    assert isinstance(queue, redis_dispatch_queue.RedisListDispatch)


@pytest.fixture(scope="module")
def redis_queue():
    try:
        queue = redis_dispatch_queue.RedisListDispatch("redis://127.0.0.1:6379/15")
        queue._client.ping()
    except Exception as exc:
        pytest.skip(f"local redis not available: {exc}")
    queue._client.flushdb()
    yield queue
    queue._client.flushdb()


def test_redis_list_dispatch_push_pop_fifo(redis_queue):
    redis_queue.push(redis_dispatch_queue.QUEUE_ANALYSIS, "first")
    redis_queue.push(redis_dispatch_queue.QUEUE_ANALYSIS, "second")
    assert redis_queue.pop(redis_dispatch_queue.QUEUE_ANALYSIS, timeout_seconds=1) == "first"
    assert redis_queue.pop(redis_dispatch_queue.QUEUE_ANALYSIS, timeout_seconds=1) == "second"
    assert redis_queue.pop(redis_dispatch_queue.QUEUE_ANALYSIS, timeout_seconds=0) is None


def test_queue_depth_returns_none_when_redis_disabled(settings):
    assert redis_dispatch_queue.queue_depth(settings, redis_dispatch_queue.QUEUE_ANALYSIS) is None
    assert redis_dispatch_queue.redis_is_enabled(settings) is False


def test_queue_depth_reports_list_length(settings):
    try:
        backend = redis_dispatch_queue.RedisListDispatch("redis://127.0.0.1:6379/15")
        backend._client.ping()
    except Exception as exc:
        pytest.skip(f"local redis not available: {exc}")

    backend._client.flushdb()
    backend.push(redis_dispatch_queue.QUEUE_ANALYSIS, "job-1")
    settings = Settings(redis_url="redis://127.0.0.1:6379/15")
    assert redis_dispatch_queue.queue_depth(settings, redis_dispatch_queue.QUEUE_ANALYSIS) == 1


def test_redis_list_dispatch_try_pop_is_nonblocking(redis_queue):
    assert redis_queue.try_pop(redis_dispatch_queue.QUEUE_ANALYSIS) is None
    redis_queue.push(redis_dispatch_queue.QUEUE_ANALYSIS, "job-1")
    assert redis_queue.try_pop(redis_dispatch_queue.QUEUE_ANALYSIS) == "job-1"
    assert redis_queue.try_pop(redis_dispatch_queue.QUEUE_ANALYSIS) is None
