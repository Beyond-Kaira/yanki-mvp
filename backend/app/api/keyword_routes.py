"""HTTP surface for Keyword Research preview (OSS / SearXNG path).

Dark when ``KEYWORD_ENABLED=0`` (404, same kill-switch stance as backlinks).
Expand is analysis-independent: seed + locale in, ideas + estimated signals out.
See ``docs/keyword-preview-oss.md``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth_dependencies import get_current_user
from app.api.keyword_schemas import (
    KeywordExpandRequest,
    KeywordExpandResponse,
    KeywordIdeaOut,
    KeywordOverviewRequest,
    KeywordOverviewResponse,
)
from app.config import Settings, get_settings
from app.db.models import User
from app.keyword.base import KeywordUnavailable
from app.keyword.registry import get_keyword_source


def require_keywords_enabled(settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """404 the module while the kill switch is off."""
    if not settings.keyword_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(
    prefix="/api/v1/keywords",
    tags=["keywords"],
    dependencies=[Depends(require_keywords_enabled)],
)


def _idea_out(idea) -> KeywordIdeaOut:
    return KeywordIdeaOut(
        phrase=idea.phrase,
        source=idea.source,
        signals=dict(idea.signals or {}),
    )


@router.post("/expand", response_model=KeywordExpandResponse)
def expand_keywords(
    body: KeywordExpandRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    _user: Annotated[User, Depends(get_current_user)],
) -> KeywordExpandResponse:
    source = get_keyword_source(settings)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="keyword expansion is enabled but no search source is configured",
        )
    max_ideas = body.max_ideas
    if max_ideas is None:
        max_ideas = int(getattr(settings, "keyword_max_ideas", 50) or 50)
    try:
        result = source.expand(
            body.seed,
            locale=body.locale,
            max_ideas=max_ideas,
            exclude_brands=body.exclude_brands or None,
        )
    except KeywordUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "keyword source unavailable",
        ) from exc
    return KeywordExpandResponse(
        seed=result.seed,
        locale=result.locale,
        provider=result.provider,
        ideas=[_idea_out(idea) for idea in result.ideas],
        estimated=True,
    )


@router.post("/overview", response_model=KeywordOverviewResponse)
def overview_keyword(
    body: KeywordOverviewRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    _user: Annotated[User, Depends(get_current_user)],
) -> KeywordOverviewResponse:
    """Thin Overview: same expand, seed signals + a short sample of ideas."""
    source = get_keyword_source(settings)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="keyword expansion is enabled but no search source is configured",
        )
    try:
        result = source.expand(
            body.keyword,
            locale=body.locale,
            max_ideas=min(12, int(getattr(settings, "keyword_max_ideas", 50) or 50)),
            exclude_brands=body.exclude_brands or None,
        )
    except KeywordUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "keyword source unavailable",
        ) from exc

    seed_signals: dict = {}
    for idea in result.ideas:
        if idea.source == "seed":
            seed_signals = dict(idea.signals or {})
            break
    sample = [_idea_out(idea) for idea in result.ideas[:8]]
    return KeywordOverviewResponse(
        keyword=result.seed,
        locale=result.locale,
        provider=result.provider,
        signals=seed_signals,
        sample_ideas=sample,
        estimated=True,
    )
