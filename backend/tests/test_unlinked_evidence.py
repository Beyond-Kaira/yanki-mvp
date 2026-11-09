"""Explicit analysis ids for unlinked mentions (mod-7)."""

from __future__ import annotations

import uuid

import pytest

from app.db.models import Analysis, ModuleRun
from app.services.unlinked_evidence import (
    UnlinkedEvidenceValidationError,
    resolve_analysis_ids_for_evidence,
)


def test_resolve_module_run_linked_analysis(db_session):
    org = uuid.uuid4()
    analysis = Analysis(org_id=org, url="https://acme.test/", status="done")
    db_session.add(analysis)
    db_session.flush()
    run = ModuleRun(
        job_kind="geo_run",
        org_id=org,
        linked_analysis_id=analysis.id,
        status="done",
    )
    db_session.add(run)
    db_session.commit()

    ids = resolve_analysis_ids_for_evidence(
        db_session,
        org_id=org,
        own_domain="acme.test",
        module_run_ids=[run.id],
    )
    assert ids == [analysis.id]


def test_resolve_rejects_other_org(db_session):
    org = uuid.uuid4()
    other = uuid.uuid4()
    analysis = Analysis(org_id=other, url="https://acme.test/")
    db_session.add(analysis)
    db_session.commit()
    with pytest.raises(UnlinkedEvidenceValidationError):
        resolve_analysis_ids_for_evidence(
            db_session,
            org_id=org,
            own_domain="acme.test",
            analysis_ids=[analysis.id],
        )
