"""`/healthz` as a readiness probe, and as the deploy gate it has always been.

Before P7.8's groundwork this endpoint returned the literal `{"status": "ok"}`,
which is not a health check — it is a check that uvicorn is accepting sockets.
`deploy.sh` and `rollback.sh` poll it and record `.last-good` when it answers,
so a release with an unreachable database was recorded as the good one to roll
back *to*.

The tests are grouped by the three claims that matter:

1. it goes red for the things that make a release unservable, and only those;
2. it stays green — and stays *informative* — for the things that are merely
   worth knowing;
3. the **body** is shaped so `deployment.sh`'s substring grep cannot pass a
   failing probe. That coupling is the one most likely to be broken by an
   innocent-looking edit, so it is pinned explicitly.
"""

from __future__ import annotations

import os
import time

import pytest
import sqlalchemy as sa

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import Analysis, Plan
from app.health import QUEUE_STALE_WARN_SECONDS


@pytest.fixture()
def pin_settings():
    """Override route settings, cleaned up after the test."""

    def _pin(**overrides):
        app.dependency_overrides[get_settings] = lambda: Settings(**overrides)

    yield _pin
    app.dependency_overrides.pop(get_settings, None)


# --------------------------------------------------------------------------
# Green, and saying something
# --------------------------------------------------------------------------


def test_a_healthy_deployment_answers_200_with_every_component_named(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["checks"]) == {
        "database",
        "schema",
        "plans",
        "queue",
        "worker",
        "providers",
    }
    assert body["checks"]["database"]["status"] == "pass"
    assert body["checks"]["plans"]["count"] == 5


def test_a_queue_backlog_is_reported_and_does_not_fail_the_probe(client, db_session):
    """Rolling a release back because customers are using it would be absurd."""

    from datetime import UTC, datetime, timedelta

    old = datetime.now(UTC) - timedelta(seconds=QUEUE_STALE_WARN_SECONDS + 60)
    db_session.add(Analysis(url="https://example.com", status="queued", created_at=old))
    db_session.commit()

    body = client.get("/healthz").json()

    assert body["status"] == "ok"
    assert body["checks"]["queue"]["status"] == "warn"
    assert body["checks"]["queue"]["queued"] == 1
    assert "worker" in body["checks"]["queue"]["detail"]


def test_missing_provider_keys_are_a_warning_under_live_mode_only(client, pin_settings):
    """`DRY_RUN` needing no keys is correct, not a fault. The deploy-time
    equivalent is `scripts/check_env.py`, which *does* fail — and which runs
    before anything is replaced, which is the right place for it."""

    pin_settings(dry_run=True)
    assert client.get("/healthz").json()["checks"]["providers"]["mode"] == "dry_run"

    pin_settings(dry_run=False, open_router_key="", tavily_api_key="")
    body = client.get("/healthz").json()
    assert body["status"] == "ok", "a missing key must not fail the probe"
    assert body["checks"]["providers"]["status"] == "warn"
    assert "OPEN_ROUTER_KEY" in body["checks"]["providers"]["detail"]


def test_an_absent_worker_is_a_warning_not_a_failure(client):
    """The api runs perfectly well with no worker — CI's e2e stack, a laptop,
    this test suite. A probe that fails there is one everybody learns to
    ignore."""

    body = client.get("/healthz").json()

    assert body["status"] == "ok"
    assert body["checks"]["worker"]["status"] == "warn"
    assert "heartbeat" in body["checks"]["worker"]["detail"]


def test_a_fresh_heartbeat_reports_the_worker_alive(client, pin_settings, tmp_path):
    from app import health

    beat_file = tmp_path / "worker.heartbeat"
    pin_settings(worker_heartbeat_path=str(beat_file))
    health.beat(Settings(worker_heartbeat_path=str(beat_file)))

    body = client.get("/healthz").json()
    assert body["checks"]["worker"]["status"] == "pass"
    assert body["checks"]["worker"]["last_beat_seconds"] < 5


def test_a_stale_heartbeat_reports_a_worker_that_stopped_looping(
    client, pin_settings, tmp_path
):
    """The defect this exists for: a `while True` that stops looping leaves the
    container "running" and the queue quietly undrained."""

    beat_file = tmp_path / "worker.heartbeat"
    beat_file.write_text("old")
    stale = time.time() - 4000
    os.utime(beat_file, (stale, stale))
    pin_settings(worker_heartbeat_path=str(beat_file), worker_heartbeat_stale_seconds=1800)

    body = client.get("/healthz").json()
    assert body["status"] == "ok", "a dead worker does not make the API unservable"
    assert body["checks"]["worker"]["status"] == "warn"
    assert body["checks"]["worker"]["last_beat_seconds"] > 1800


# --------------------------------------------------------------------------
# Red, for the things that mean nobody can be served
# --------------------------------------------------------------------------


def test_an_empty_plan_catalog_fails_the_probe_while_enforcement_is_on(
    client, db_session, pin_settings
):
    """With enforcement on, an empty catalog makes every metered route answer
    503 (ADR-45) — the release cannot serve, and the deploy gate should say so
    rather than record it as last-good."""

    db_session.execute(sa.delete(Plan))
    db_session.commit()
    pin_settings(quota_enforcement_enabled=True)

    response = client.get("/healthz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["plans"]["status"] == "fail"


def test_an_empty_catalog_is_only_a_warning_while_enforcement_is_off(
    client, db_session, pin_settings
):
    """A probe that fails on a condition with no consequence trains people to
    ignore it."""

    db_session.execute(sa.delete(Plan))
    db_session.commit()
    pin_settings(quota_enforcement_enabled=False)

    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["checks"]["plans"]["status"] == "warn"


# --------------------------------------------------------------------------
# The body is the deploy gate's contract
# --------------------------------------------------------------------------


def test_an_unhealthy_body_contains_no_ok_anywhere(client, db_session, pin_settings):
    """`deployment.sh` greps the body for the substrings `status` AND `ok`
    rather than trusting the status code.

    So a failing body containing "ok" anywhere — a field named `"ok": false`, a
    detail mentioning a "token", a message about something "broken" — would pass
    the gate it exists to fail, and a bad release would be recorded as
    last-good. This is the test that notices when somebody renames a field.
    """

    db_session.execute(sa.delete(Plan))
    db_session.commit()
    pin_settings(quota_enforcement_enabled=True)

    response = client.get("/healthz")
    assert response.status_code == 503
    assert "ok" not in response.text.casefold(), response.text


def test_a_healthy_body_still_contains_both_markers_the_gate_greps(client):
    """The other half of the same contract — and the reason the healthy shape
    could not simply be replaced with something tidier."""

    body = client.get("/healthz").text
    assert "status" in body
    assert "ok" in body


# --------------------------------------------------------------------------
# The public edge sees the verdict, not the reasons
# --------------------------------------------------------------------------


def test_a_request_through_the_public_edge_gets_the_status_and_no_detail(client):
    """nginx routes /healthz from the internet. The component breakdown names
    the schema revision, the queue depth, whether provider keys are set and how
    stale the worker is — none of it a credential, none of it worth handing to
    anybody who asks. `X-Forwarded-For` is what the edge adds and the loopback
    deploy gate does not."""

    response = client.get("/healthz", headers={"X-Forwarded-For": "203.0.113.9"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_public_verdict_matches_the_internal_one(client, db_session, pin_settings):
    """Only the reasons are withheld. A release that is unhealthy internally
    must be unhealthy at the edge, or the two gates disagree about the same
    deploy."""

    db_session.execute(sa.delete(Plan))
    db_session.commit()
    pin_settings(quota_enforcement_enabled=True)

    public = client.get("/healthz", headers={"X-Forwarded-For": "203.0.113.9"})
    internal = client.get("/healthz")

    assert public.status_code == internal.status_code == 503
    assert public.json()["status"] == internal.json()["status"] == "unhealthy"
    assert "checks" not in public.json()
    assert "ok" not in public.text.casefold()
