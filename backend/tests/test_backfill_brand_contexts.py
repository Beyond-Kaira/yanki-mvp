"""Backfill analyses.kyc → brand_contexts (action 18)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models import Analysis, BrandContext
from app.services.backfill_brand_contexts import (
    backfill_analysis_brand_contexts,
    fields_from_analysis_kyc,
)


def test_fields_from_analysis_kyc_uses_url_and_lang(db_session):
    analysis = Analysis(
        url="https://www.acme.test/about",
        lang="tr",
        brand="Acme",
        kyc={
            "company": "Acme Robotics",
            "category": "robotics",
            "competitors": ["Globex"],
        },
    )
    fields = fields_from_analysis_kyc(analysis)
    assert fields is not None
    assert fields["brand"] == "Acme Robotics"
    assert fields["domain"] == "acme.test"
    assert fields["locale"] == "tr"
    assert fields["competitors"] == ["Globex"]
    assert fields["profile"]["company"] == "Acme Robotics"


def test_fields_from_analysis_kyc_returns_none_without_company(db_session):
    analysis = Analysis(url="https://x.test", kyc={"description": "no name"})
    assert fields_from_analysis_kyc(analysis) is None


def test_backfill_links_and_skips(db_session):
    good = Analysis(
        url="https://good.test",
        kyc={"company": "Good Co", "competitors": []},
    )
    bad = Analysis(url="https://bad.test", kyc={"keywords": ["only"]})
    already = Analysis(
        url="https://linked.test",
        kyc={"company": "Linked Co"},
    )
    db_session.add_all([good, bad, already])
    db_session.flush()

    ctx = BrandContext(brand="Linked Co", profile={"company": "Linked Co"})
    db_session.add(ctx)
    db_session.flush()
    already.brand_context_id = ctx.id
    db_session.commit()

    stats = backfill_analysis_brand_contexts(db_session, dry_run=False)
    db_session.commit()

    assert stats.scanned == 2
    assert stats.linked == 1
    assert stats.skipped == 1

    row = db_session.execute(select(Analysis).where(Analysis.id == good.id)).scalar_one()
    assert row.brand_context_id is not None
    loaded = db_session.get(BrandContext, row.brand_context_id)
    assert loaded is not None
    assert loaded.brand == "Good Co"
    assert loaded.org_id is None


def test_backfill_respects_org_filter(db_session):
    org = uuid.uuid4()
    other = uuid.uuid4()
    a1 = Analysis(org_id=org, url="https://a.test", kyc={"company": "A"})
    a2 = Analysis(org_id=other, url="https://b.test", kyc={"company": "B"})
    db_session.add_all([a1, a2])
    db_session.commit()

    stats = backfill_analysis_brand_contexts(db_session, org_id=org, dry_run=False)
    db_session.commit()

    assert stats.scanned == 1
    assert stats.linked == 1
    db_session.refresh(a1)
    db_session.refresh(a2)
    assert a1.brand_context_id is not None
    assert a2.brand_context_id is None


def test_backfill_dry_run_no_writes(db_session):
    analysis = Analysis(url="https://dry.test", kyc={"company": "Dry Co"})
    db_session.add(analysis)
    db_session.commit()

    stats = backfill_analysis_brand_contexts(db_session, dry_run=True)
    db_session.refresh(analysis)
    assert stats.linked == 1
    assert analysis.brand_context_id is None
    assert db_session.scalar(select(BrandContext)) is None
