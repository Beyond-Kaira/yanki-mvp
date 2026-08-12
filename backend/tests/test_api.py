"""API route tests (FastAPI TestClient, in-process, SQLite-backed)."""

import uuid
from decimal import Decimal

from app.db.models import Analysis, Prompt, Response


def test_submitting_an_analysis_requires_a_credential(client, db_session):
    """The route was open until P7.6 and no page had used it that way since
    session 21 moved the URL form behind sign-in (ADR-45). An endpoint that
    spends money at a paid vendor cannot be metered while anyone can call it."""

    resp = client.post("/api/v1/analyses", json={"url": "https://acme.test"})

    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"
    assert db_session.query(Analysis).count() == 0


def test_submit_valid_url_returns_202_and_queued_row(client, db_session, signed_in):
    _, org = signed_in()
    resp = client.post("/api/v1/analyses", json={"url": "https://acme.test"})

    assert resp.status_code == 202
    body = resp.json()
    assert "id" in body

    analysis = db_session.get(Analysis, uuid.UUID(body["id"]))
    assert analysis is not None
    assert analysis.status == "queued"
    assert analysis.progress == 0
    # The run belongs to the organization that started it — the attribution that
    # makes metering, and later a per-org history, possible at all.
    assert analysis.org_id == org.id


def test_submit_invalid_url_returns_422(client, signed_in):
    signed_in()
    resp = client.post("/api/v1/analyses", json={"url": "not-a-url"})
    assert resp.status_code == 422


def test_submit_ssrf_target_is_rejected(client, db_session, signed_in):
    # Loopback / link-local (cloud metadata) hosts must not be accepted for the
    # worker to fetch — reject them at the boundary.
    signed_in()
    for url in (
        "http://127.0.0.1:8000/",
        "http://169.254.169.254/latest/meta-data/",
    ):
        resp = client.post("/api/v1/analyses", json={"url": url})
        assert resp.status_code == 422, url

    # Nothing was enqueued.
    assert db_session.query(Analysis).count() == 0


def test_submit_missing_url_returns_422(client, signed_in):
    signed_in()
    resp = client.post("/api/v1/analyses", json={})
    assert resp.status_code == 422


def test_get_unknown_id_returns_404(client):
    resp = client.get(f"/api/v1/analyses/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_returns_thin_envelope_without_nested_result(client, make_analysis):
    analysis = make_analysis(url="https://acme.test")

    resp = client.get(f"/api/v1/analyses/{analysis.id}")
    assert resp.status_code == 200

    body = resp.json()
    assert body["id"] == str(analysis.id)
    assert body["url"] == "https://acme.test"
    assert body["status"] == "queued"
    assert body["progress"] == 0
    assert body["current_step"] is None
    assert body["error"] is None
    assert "result" not in body
    assert body["geo_score"] is None
    assert body["footprint_count"] is None
    assert body["total_responses"] is None


def test_get_done_analysis_thin_envelope_carries_summary_columns(client, db_session, make_analysis):
    analysis = make_analysis(
        url="https://acme.test",
        status="done",
        progress=100,
        kyc={"company": "Acme", "industry": "Robotics"},
        geo_score=0.5,
        footprint_count=1,
        total_responses=2,
    )
    prompt = Prompt(
        analysis_id=analysis.id, text="Best warehouse robots?", category="recommendation"
    )
    db_session.add(prompt)
    db_session.flush()
    db_session.add_all(
        [
            Response(
                analysis_id=analysis.id,
                prompt_id=prompt.id,
                engine="anthropic",
                model="claude",
                raw_text="Acme is a strong option.",
                footprint=True,
                matched_snippet="Acme is a strong option.",
                cost_usd=Decimal("0.001234"),
            ),
            Response(
                analysis_id=analysis.id,
                prompt_id=prompt.id,
                engine="openai",
                model="gpt",
                raw_text="Plenty of vendors exist.",
                footprint=False,
                matched_snippet=None,
                cost_usd=Decimal("0"),
            ),
        ]
    )
    db_session.commit()
    analysis_id = analysis.id

    resp = client.get(f"/api/v1/analyses/{analysis_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert "result" not in body
    assert body["geo_score"] == 0.5
    assert body["footprint_count"] == 1
    assert body["total_responses"] == 2

    assert client.get(f"/api/v1/analyses/{analysis_id}/kyc").json()["kyc"] == {
        "company": "Acme",
        "industry": "Robotics",
    }
    prompts = client.get(f"/api/v1/analyses/{analysis_id}/prompts").json()["prompts"]
    assert len(prompts) == 1
    assert prompts[0]["id"] == str(prompt.id)
    geo = client.get(f"/api/v1/analyses/{analysis_id}/geo").json()
    assert len(geo["responses"]) == 2
    hit = next(r for r in geo["responses"] if r["engine"] == "anthropic")
    assert hit["cost_usd"] == 0.001234


def test_get_reports_no_serp_summary_when_the_run_never_measured_it(client, make_analysis):
    """ADR-28: a null summary means "we did not look", never "we found nothing"."""
    analysis = make_analysis()

    body = client.get(f"/api/v1/analyses/{analysis.id}").json()

    assert body["serp_status"] is None
    assert client.get(f"/api/v1/analyses/{analysis.id}/serp").json() is None


def test_get_serializes_the_serp_summary_and_its_evidence(client, db_session, make_analysis):
    from app.db.models import SerpCheck

    analysis = make_analysis(
        status="done",
        serp_status="ok",
        serp_source="searxng",
        serp_score=0.5,
        serp_hit_count=1,
        serp_query_count=2,
    )
    db_session.add_all(
        [
            SerpCheck(
                analysis_id=analysis.id,
                query="best warehouse robots",
                source="searxng",
                hit=True,
                rank=3,
                matched_url="https://acme.example/",
                matched_snippet="Acme Robotics — Home",
                matched_via="domain",
                result_count=10,
            ),
            SerpCheck(
                analysis_id=analysis.id,
                query="warehouse robots comparison",
                source="searxng",
                hit=False,
                result_count=10,
            ),
        ]
    )
    db_session.commit()

    serp = client.get(f"/api/v1/analyses/{analysis.id}/serp").json()

    assert serp["status"] == "ok"
    assert serp["source"] == "searxng"
    assert serp["score"] == 0.5
    assert (serp["hits"], serp["queries"]) == (1, 2)
    assert len(serp["checks"]) == 2
    hit = next(check for check in serp["checks"] if check["hit"])
    assert hit["rank"] == 3
    assert hit["matched_via"] == "domain"


def test_a_measured_but_unreadable_run_serializes_a_null_score(client, make_analysis):
    """Present summary, null score — "we looked and could not see"."""
    analysis = make_analysis(
        status="done",
        serp_status="unavailable",
        serp_source="searxng",
        serp_hit_count=0,
        serp_query_count=0,
    )

    serp = client.get(f"/api/v1/analyses/{analysis.id}/serp").json()

    assert serp["status"] == "unavailable"
    assert serp["score"] is None
    assert serp["checks"] == []


def test_get_reports_no_seo_audit_when_the_run_never_audited(client, make_analysis):
    """ADR-31: a checker submission has no site, so there is nothing to grade."""
    analysis = make_analysis()

    assert client.get(f"/api/v1/analyses/{analysis.id}/seo").json() is None


def test_get_serializes_the_seo_audit_and_its_checks(client, db_session, make_analysis):
    from app.db.models import SeoCheck

    analysis = make_analysis(status="done", seo_status="ok", seo_score=61.4, seo_grade="C")
    db_session.add_all(
        [
            SeoCheck(
                analysis_id=analysis.id,
                check_id="ai_crawler_access",
                title="AI crawlers can read the site",
                severity="critical",
                status="fail",
                detail="robots.txt blocks crawlers answer engines use.",
                evidence="Blocked: OAI-SearchBot (ChatGPT Search)",
            ),
            SeoCheck(
                analysis_id=analysis.id,
                check_id="image_alt",
                title="Images have alt text",
                severity="minor",
                status="not_applicable",
                detail="The crawled pages have no images.",
            ),
        ]
    )
    db_session.commit()

    seo = client.get(f"/api/v1/analyses/{analysis.id}/seo").json()

    assert seo["status"] == "ok"
    assert seo["grade"] == "C"
    assert seo["score"] == 61.4
    assert len(seo["checks"]) == 2
    blocked = next(c for c in seo["checks"] if c["check_id"] == "ai_crawler_access")
    assert blocked["severity"] == "critical"
    assert blocked["status"] == "fail"
    assert "OAI-SearchBot" in blocked["evidence"]
    # not_applicable survives the round trip as itself, not as a failure.
    assert next(c for c in seo["checks"] if c["check_id"] == "image_alt")["status"] == (
        "not_applicable"
    )
