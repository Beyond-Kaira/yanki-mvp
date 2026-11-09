"""Job dispatch broker facade (rq-2).

``redis_dispatch_queue`` is the implementation: Redis list dispatch when
``REDIS_URL`` is set, otherwise a no-op backend and Postgres ``claim_next*``.
"""

from __future__ import annotations

from app.jobs.redis_dispatch_queue import (
    DEFAULT_POP_TIMEOUT_SECONDS,
    QUEUE_ANALYSIS,
    QUEUE_MODULE,
    QUEUE_SITE_AUDIT,
    JobDispatchBackend,
    PostgresFallbackDispatch,
    RedisListDispatch,
    connect_from_settings,
    notify_analysis_enqueued,
    notify_module_run_enqueued,
    notify_site_audit_enqueued,
    ping_redis,
    queue_depth,
    redis_is_enabled,
)

__all__ = [
    "DEFAULT_POP_TIMEOUT_SECONDS",
    "QUEUE_ANALYSIS",
    "QUEUE_MODULE",
    "QUEUE_SITE_AUDIT",
    "JobDispatchBackend",
    "PostgresFallbackDispatch",
    "RedisListDispatch",
    "connect_from_settings",
    "get_broker",
    "notify_analysis_enqueued",
    "notify_module_run_enqueued",
    "notify_site_audit_enqueued",
    "ping_redis",
    "queue_depth",
    "redis_is_enabled",
]


def get_broker(settings):  # noqa: ANN001 — Settings from app.config
    return connect_from_settings(settings)
