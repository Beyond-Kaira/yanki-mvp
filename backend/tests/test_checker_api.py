"""Checker API tests (P5.1): submit + 24h per-brand reuse + per-submit leads.

Runs against the in-memory SQLite fixture like the rest of the API suite. All
under DRY_RUN semantics — no worker runs here, so a "cache hit" is simulated by
marking a submitted analysis ``done`` in the DB before the repeat submit.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import Analysis, CheckerSubmission


@pytest.fixture(autouse=True)
def _enable_checker():
    """Open the checker with permissive P5.6 guards for the P5.1 behavior suite.

    P5.6 defaults ``checker_enabled`` OFF (a fresh submit → parked 503), so these
    submit/reuse/lead tests — which predate and are orthogonal to the guards —
    pin the endpoint ON with wide-open limits and cost cap. The guards themselves
    are exercised in ``test_checker_ratelimit.py``. Cleared by the ``client``
    fixture's teardown, which clears all dependency overrides.
    """
    app.dependency_overrides[get_settings] = lambda: Settings(
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=10_000,
        checker_rate_limit_per_brand_day=10_000,
        checker_daily_usd_cap=1_000_000.0,
    )


def _submit(client, brand="Nike", category="Running Shoes", lang="en"):
    return client.post(
        "/api/v1/checker",
        json={"brand": brand, "category": category, "lang": lang},
    )


def _mark_done(db_session, analysis_id):
    row = db_session.get(Analysis, uuid.UUID(str(analysis_id)))
    row.status = "done"
    db_session.commit()
    return row


# --- submit --------------------------------------------------------------------


def test_submit_returns_202_with_id_and_submission_id(client, db_session):
    resp = _submit(client)
    assert resp.status_code == 202
    body = resp.json()
    assert "id" in body and "submission_id" in body

    analysis = db_session.get(Analysis, uuid.UUID(body["id"]))
    assert analysis is not None
    assert analysis.kind == "checker"
    assert analysis.status == "queued"
    # Synthetic, non-null, deterministic, normalized url satisfies NOT NULL.
    assert analysis.url == "checker://nike/running shoes"
    # brand/category/lang stored normalized (trim + casefold).
    assert analysis.brand == "nike"
    assert analysis.category == "running shoes"
    assert analysis.lang == "en"

    submission = db_session.get(CheckerSubmission, uuid.UUID(body["submission_id"]))
    assert submission is not None
    assert submission.analysis_id == analysis.id
    # P5.6 populates ip_hash with a salted hash of the client IP (never the raw
    # IP); the salted-not-raw contract is exercised in test_checker_ratelimit.py.
    assert submission.ip_hash is not None
    assert submission.email is None


def test_blank_brand_returns_422_and_records_nothing(client, db_session):
    resp = _submit(client, brand="   ")
    assert resp.status_code == 422
    assert db_session.query(Analysis).count() == 0
    assert db_session.query(CheckerSubmission).count() == 0


def test_blank_category_returns_422_and_records_nothing(client, db_session):
    resp = _submit(client, category="")
    assert resp.status_code == 422
    assert db_session.query(Analysis).count() == 0
    assert db_session.query(CheckerSubmission).count() == 0


# --- 24h reuse -----------------------------------------------------------------


def test_repeat_within_24h_reuses_analysis_but_records_submission(client, db_session):
    first = _submit(client)
    analysis_id = first.json()["id"]
    _mark_done(db_session, analysis_id)

    assert db_session.query(Analysis).count() == 1
    assert db_session.query(CheckerSubmission).count() == 1

    # A repeat submit of the same normalized triple hits the cache.
    second = _submit(client, brand="  NIKE ", category="running shoes")
    assert second.status_code == 202
    assert second.json()["id"] == analysis_id  # same analysis
    # No new analyses row, but a new submission row (cache hits count as demand).
    assert db_session.query(Analysis).count() == 1
    assert db_session.query(CheckerSubmission).count() == 2
    assert second.json()["submission_id"] != first.json()["submission_id"]


def test_expired_done_analysis_is_not_reused(client, db_session):
    first = _submit(client)
    analysis_id = first.json()["id"]
    row = _mark_done(db_session, analysis_id)
    # Backdate past the 24h window.
    row.created_at = datetime.now(UTC) - timedelta(hours=25)
    db_session.commit()

    second = _submit(client)
    assert second.status_code == 202
    assert second.json()["id"] != analysis_id  # a fresh row, not the stale one
    assert db_session.query(Analysis).count() == 2


def test_recent_but_not_done_analysis_is_not_reused(client, db_session):
    # A queued/failed recent run is NOT a cache hit — reuse requires status=done.
    # (A concurrent in-flight run may thus create a second row; acceptable at MVP.)
    first = _submit(client)  # stays 'queued'
    analysis_id = first.json()["id"]

    second = _submit(client)
    assert second.json()["id"] != analysis_id
    assert db_session.query(Analysis).count() == 2

    # A failed recent run is likewise not reused.
    failed = db_session.get(Analysis, uuid.UUID(analysis_id))
    failed.status = "failed"
    db_session.commit()
    third = _submit(client)
    assert third.json()["id"] not in {analysis_id, second.json()["id"]}


# --- leads (append-only) -------------------------------------------------------


def test_two_emails_on_same_cached_analysis_both_persist(client, db_session):
    first = _submit(client)
    analysis_id = first.json()["id"]
    sub_a = first.json()["submission_id"]
    _mark_done(db_session, analysis_id)

    second = _submit(client)  # cache hit — same analysis, new submission
    assert second.json()["id"] == analysis_id
    sub_b = second.json()["submission_id"]
    assert sub_a != sub_b

    r1 = client.post("/api/v1/checker/leads", json={"submission_id": sub_a, "email": "a@x.com"})
    r2 = client.post("/api/v1/checker/leads", json={"submission_id": sub_b, "email": "b@y.com"})
    assert r1.status_code == 202
    assert r2.status_code == 202

    row_a = db_session.get(CheckerSubmission, uuid.UUID(sub_a))
    row_b = db_session.get(CheckerSubmission, uuid.UUID(sub_b))
    # Both leads persist on their own submission — no overwrite on the shared row.
    assert row_a.email == "a@x.com"
    assert row_b.email == "b@y.com"


def test_relead_same_submission_overwrites_own_row(client, db_session):
    # Re-posting a lead for the SAME submission updates that one row (deliberate:
    # a visitor correcting their email), never touching any other submission.
    first = _submit(client)
    sub = first.json()["submission_id"]

    r1 = client.post("/api/v1/checker/leads", json={"submission_id": sub, "email": "old@x.com"})
    r2 = client.post("/api/v1/checker/leads", json={"submission_id": sub, "email": "new@x.com"})
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert db_session.get(CheckerSubmission, uuid.UUID(sub)).email == "new@x.com"


def test_lead_unknown_submission_returns_404(client):

    resp = client.post(
        "/api/v1/checker/leads",
        json={"submission_id": str(uuid.uuid4()), "email": "a@x.com"},
    )
    assert resp.status_code == 404


def test_lead_invalid_email_returns_422(client, db_session):
    first = _submit(client)
    sub = first.json()["submission_id"]
    resp = client.post(
        "/api/v1/checker/leads", json={"submission_id": sub, "email": "not-an-email"}
    )
    assert resp.status_code == 422

    assert db_session.get(CheckerSubmission, uuid.UUID(sub)).email is None


# --- MVP unchanged -------------------------------------------------------------


def test_mvp_submit_defaults_kind_to_mvp(client, db_session, signed_in):
    # The MVP submit route needs a credential from P7.6 on (ADR-45); the checker
    # route above deliberately still does not, which is the distinction this
    # section exists to keep visible.
    signed_in(email="mvp-kind@example.test")

    resp = client.post("/api/v1/analyses", json={"url": "https://acme.test"})
    assert resp.status_code == 202
    row = db_session.get(Analysis, uuid.UUID(resp.json()["id"]))
    assert row.kind == "mvp"
    assert row.brand is None
    assert row.category is None
    assert row.lang == "en"


def test_checker_row_flows_through_get_unchanged(client):
    # The existing GET envelope works for a checker row: synthetic url shown.
    body = _submit(client).json()
    resp = client.get(f"/api/v1/analyses/{body['id']}")
    assert resp.status_code == 200
    got = resp.json()
    assert got["url"] == "checker://nike/running shoes"
    assert got["status"] == "queued"
    assert "result" not in got
    assert client.get(f"/api/v1/analyses/{body['id']}/kyc").json()["kyc"] is None
