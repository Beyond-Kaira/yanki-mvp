"""Resolve explicit analysis ids for mod-7 unlinked-mentions joins."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Analysis, ModuleRun


class UnlinkedEvidenceValidationError(Exception):
    """Caller-facing 422."""


def resolve_analysis_ids_for_evidence(
    session: Session,
    *,
    org_id: uuid.UUID,
    own_domain: str,
    analysis_ids: list[uuid.UUID] | None = None,
    module_run_ids: list[uuid.UUID] | None = None,
) -> list[uuid.UUID]:
    """Return analysis ids to scan for citation/SERP evidence (mod-7).

    When both ``analysis_ids`` and ``module_run_ids`` are omitted, callers fall
    back to legacy domain matching in ``unlinked_mentions``.
    """

    from app.backlink.normalize import domain_key

    own = domain_key(own_domain) or own_domain
    resolved: list[uuid.UUID] = []

    if analysis_ids:
        for aid in analysis_ids:
            row = session.get(Analysis, aid)
            if row is None or row.org_id != org_id:
                raise UnlinkedEvidenceValidationError(f"analysis {aid} not found")
            host = domain_key(row.url)
            if host != own:
                raise UnlinkedEvidenceValidationError(
                    f"analysis {aid} url host does not match project domain"
                )
            resolved.append(aid)

    if module_run_ids:
        for run_id in module_run_ids:
            run = session.get(ModuleRun, run_id)
            if run is None or run.org_id != org_id:
                raise UnlinkedEvidenceValidationError(f"module run {run_id} not found")
            if run.linked_analysis_id is None:
                raise UnlinkedEvidenceValidationError(
                    f"module run {run_id} has no linked_analysis_id"
                )
            linked = session.get(Analysis, run.linked_analysis_id)
            if linked is None or linked.org_id != org_id:
                raise UnlinkedEvidenceValidationError(
                    f"linked analysis for run {run_id} not found"
                )
            host = domain_key(linked.url)
            if host != own:
                raise UnlinkedEvidenceValidationError(
                    f"module run {run_id} linked analysis domain mismatch"
                )
            resolved.append(run.linked_analysis_id)

    # Preserve order, drop duplicates.
    seen: set[uuid.UUID] = set()
    unique: list[uuid.UUID] = []
    for aid in resolved:
        if aid not in seen:
            seen.add(aid)
            unique.append(aid)
    return unique
