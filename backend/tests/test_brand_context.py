"""BrandContext entity (ADR-52 / mod-1)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models import Analysis, BrandContext


def test_brand_context_persists_and_links_analysis(db_session):
    ctx = BrandContext(
        brand="Acme Pay",
        domain="acmepay.com",
        locale="en",
        category="money transfer",
        competitors=["Wise", "Remitly"],
        profile={"company": "Acme Pay", "competitors": ["Wise", "Remitly"]},
        source_url="https://acmepay.com",
    )
    db_session.add(ctx)
    db_session.flush()

    analysis = Analysis(url="https://acmepay.com", brand_context_id=ctx.id)
    db_session.add(analysis)
    db_session.commit()

    loaded = db_session.execute(select(BrandContext).where(BrandContext.id == ctx.id)).scalar_one()
    assert loaded.brand == "Acme Pay"
    assert loaded.competitors == ["Wise", "Remitly"]
    assert loaded.profile["company"] == "Acme Pay"

    row = db_session.execute(select(Analysis).where(Analysis.id == analysis.id)).scalar_one()
    assert row.brand_context_id == ctx.id
    assert row.brand_context is not None
    assert row.brand_context.brand == "Acme Pay"


def test_analysis_brand_context_unlink_on_delete(db_session):
    ctx_id = uuid.uuid4()
    ctx = BrandContext(id=ctx_id, brand="Temp Co")
    db_session.add(ctx)
    db_session.flush()

    analysis = Analysis(url="https://temp.co", brand_context_id=ctx_id)
    db_session.add(analysis)
    db_session.commit()

    db_session.delete(ctx)
    db_session.commit()

    row = db_session.execute(select(Analysis).where(Analysis.id == analysis.id)).scalar_one()
    assert row.brand_context_id is None
