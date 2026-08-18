"""Rate-limit tests for the LIVE POST /api/v1/analyses (P5.0).

The endpoint runs with real keys in prod, so a throttled client must be rejected
with a 429 BEFORE any analyses row is created. These run against the in-memory
SQLite fixture like the rest of the API suite.

Since P7.6 the route also requires a credential and consumes a plan quota
(ADR-45), which is why every test here signs in on an **unlimited** tier. That
is not a convenience: both guards answer 429, so a test whose org could run out
of allowance would no longer be able to tell which limit refused it. Pinning the
plan to unlimited leaves exactly one thing in this file that can produce a 429.
The reverse case — the plan refusing while the rate limit is untouched — is
``test_quota_enforcement.py``'s.
"""

import pytest

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import Analysis
from app.services.rate_limit import hash_ip

VALID_URL = "https://example.com"


@pytest.fixture(autouse=True)
def unlimited_submitter(signed_in):
    signed_in(email="rate-limit@example.test", plan_key="enterprise")


def _submit(client, ip: str | None = None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post("/api/v1/analyses", json={"url": VALID_URL}, headers=headers)


def _override_settings(**kwargs):
    """Pin route settings for a test (cleared by the client fixture teardown)."""
    defaults: dict[str, object] = {"user_analysis_limit": 0}
    defaults.update(kwargs)
    settings = Settings(**defaults)
    app.dependency_overrides[get_settings] = lambda: settings


@pytest.fixture(autouse=True)
def lift_user_stock_limit():
    _override_settings()
    yield
    app.dependency_overrides.pop(get_settings, None)


def test_sixth_submit_from_one_ip_returns_429_with_retry_after(client, db_session):
    ip = "203.0.113.7"
    for _ in range(5):  # default per-IP limit is 5/hour
        assert _submit(client, ip).status_code == 202

    resp = _submit(client, ip)
    assert resp.status_code == 429
    retry_after = resp.headers.get("Retry-After")
    assert retry_after is not None
    # Plausible: a slot frees no later than the 1-hour window end.
    assert 1 <= int(retry_after) <= 3600
    # The throttled submit must NOT create a row (no queued work => no spend).
    # This also fails loudly if the limit check is ever moved AFTER create.
    assert db_session.query(Analysis).count() == 5


def test_submits_under_limit_persist_ip_hash(client, db_session):
    ip = "198.51.100.42"
    resp = _submit(client, ip)
    assert resp.status_code == 202

    rows = db_session.query(Analysis).all()
    assert len(rows) == 1
    # Stored value is the salted hash (default empty salt), never the raw IP.
    assert rows[0].ip_hash == hash_ip(ip, "")
    assert rows[0].ip_hash != ip


def test_daily_cap_breach_returns_429_even_from_a_fresh_ip(client):
    # Low global cap, high per-IP so only the daily cap can trip.
    _override_settings(analyses_daily_cap=3, analyses_rate_limit_per_ip_hour=1000)

    for _ in range(3):
        assert _submit(client, "192.0.2.1").status_code == 202

    # A brand-new IP is still refused once the global cap is reached.
    resp = _submit(client, "192.0.2.99")
    assert resp.status_code == 429
    assert 1 <= int(resp.headers["Retry-After"]) <= 24 * 3600


def test_different_ips_are_independent(client):
    ip_a = "203.0.113.10"
    for _ in range(5):
        assert _submit(client, ip_a).status_code == 202
    # ip_a is now at its limit...
    assert _submit(client, ip_a).status_code == 429
    # ...but a different IP has its own fresh bucket.
    assert _submit(client, "203.0.113.11").status_code == 202


def test_xff_is_honored_over_socket_peer(client):
    # The socket peer is a constant "testclient" for every request; if XFF were
    # ignored, all requests would share one bucket. Fill one XFF bucket to its
    # limit, then prove a different XFF value is unaffected.
    for _ in range(5):
        assert _submit(client, "203.0.113.20").status_code == 202
    assert _submit(client, "203.0.113.20").status_code == 429
    assert _submit(client, "203.0.113.21").status_code == 202


def test_zero_limit_is_a_kill_switch_not_a_500(client, db_session):
    # Setting either limit to 0 must reject every submit with a clean 429
    # (an operational kill-switch), never crash on the empty window.
    _override_settings(analyses_rate_limit_per_ip_hour=0)
    resp = _submit(client, "203.0.113.40")
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) == 3600

    _override_settings(analyses_rate_limit_per_ip_hour=1000, analyses_daily_cap=0)
    resp = _submit(client, "203.0.113.41")
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) == 24 * 3600
    assert db_session.query(Analysis).count() == 0


def test_422_submits_do_not_count_toward_the_limit(client):
    ip = "203.0.113.30"
    # SSRF/loopback targets are rejected 422 and create no row, so they must not
    # consume the rate-limit budget however many are sent.
    for _ in range(20):
        r = client.post(
            "/api/v1/analyses",
            json={"url": "http://127.0.0.1/"},
            headers={"X-Forwarded-For": ip},
        )
        assert r.status_code == 422
    # A valid submit from the same IP still succeeds.
    assert _submit(client, ip).status_code == 202
