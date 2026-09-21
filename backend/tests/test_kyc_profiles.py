"""Standalone KYC / BrandContext profiles API (mod-5)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db.models import Analysis, BrandContext, ModuleRun
from app.pipeline import discovery
from app.pipeline.discovery import CrawlResult

PROFILES = "/api/v1/kyc/profiles"


@pytest.fixture
def allow_test_urls(monkeypatch):
    from app.services import brand_contexts

    def guard(url: str) -> bool:
        if ".test" in url:
            return True
        return brand_contexts.is_public_url(url)

    monkeypatch.setattr(brand_contexts, "is_public_url", guard)


def test_create_manual_profile(client, signed_in):
    signed_in()
    response = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer", "competitors": ["Wise"]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["brand"] == "Acme Pay"
    assert body["category"] == "money transfer"
    assert body["competitors"] == ["Wise"]
    assert body["profile"]["company"] == "Acme Pay"
    assert body["org_id"] is not None


def test_read_and_patch_profile(client, signed_in):
    signed_in()
    created = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer", "keywords": ["remittance"]},
    ).json()
    profile_id = created["id"]

    read = client.get(f"{PROFILES}/{profile_id}")
    assert read.status_code == 200
    assert read.json()["brand"] == "Acme Pay"

    patched = client.patch(
        f"{PROFILES}/{profile_id}",
        json={"brand": "Acme Payments", "competitors": ["Wise", "Remitly"]},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["brand"] == "Acme Payments"
    assert body["competitors"] == ["Wise", "Remitly"]
    assert body["profile"]["company"] == "Acme Payments"


def test_create_from_source_url(client, signed_in, allow_test_urls, monkeypatch):
    signed_in()

    def fake_discover(_url: str) -> CrawlResult:
        return CrawlResult(
            text="Acme Pay offers international money transfer services worldwide.",
        )

    monkeypatch.setattr(discovery, "discover_detailed", fake_discover)

    response = client.post(
        PROFILES,
        json={"source_url": "https://acme.test/", "locale": "en"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source_url"] == "https://acme.test/"
    assert body["domain"] == "acme.test"
    assert body["brand"]
    assert body["profile"]


def test_create_requires_brand_or_source_url(client, signed_in):
    signed_in()
    response = client.post(PROFILES, json={"locale": "en"})
    assert response.status_code == 422


def test_patch_requires_a_field(client, signed_in):
    signed_in()
    created = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer"},
    ).json()
    response = client.patch(f"{PROFILES}/{created['id']}", json={})
    assert response.status_code == 422


def test_profile_is_org_scoped(client, signed_in):
    signed_in(email="owner-a@example.test")
    created = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer"},
    ).json()

    signed_in(email="owner-b@example.test")
    assert client.get(f"{PROFILES}/{created['id']}").status_code == 404
    assert client.patch(
        f"{PROFILES}/{created['id']}",
        json={"brand": "Hijacked"},
    ).status_code == 404


def test_create_profile_does_not_enqueue_analysis(client, signed_in, db_session):
    signed_in()
    before = len(db_session.scalars(select(Analysis.id)).all())
    response = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer"},
    )
    assert response.status_code == 201
    after = len(db_session.scalars(select(Analysis.id)).all())
    assert after == before


def test_unknown_profile_is_404(client, signed_in):
    signed_in()
    assert client.get(f"{PROFILES}/{uuid.uuid4()}").status_code == 404


def test_enqueue_extract_returns_module_run(client, signed_in, allow_test_urls, db_session):
    signed_in()
    created = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer", "domain": "acme.test"},
    ).json()

    response = client.post(
        f"{PROFILES}/{created['id']}/extract",
        json={"source_url": "https://acme.test/"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_kind"] == "kyc_extract"
    assert body["status"] == "queued"
    assert body["brand_context_id"] == created["id"]

    run = db_session.get(ModuleRun, uuid.UUID(body["id"]))
    assert run is not None
    assert run.payload["source_url"] == "https://acme.test/"


def test_extract_requires_source_url_when_profile_has_none(client, signed_in):
    signed_in()
    created = client.post(
        PROFILES,
        json={"brand": "Acme Pay", "category": "money transfer"},
    ).json()

    response = client.post(f"{PROFILES}/{created['id']}/extract", json={})
    assert response.status_code == 422
