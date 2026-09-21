"""BrandContext CRUD — standalone KYC profiles (ADR-52 / mod-5)."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import BrandContext
from app.net_guard import is_public_url
from app.pipeline import discovery
from app.pipeline.errors import PipelineError
from app.pipeline.kyc import KYC, generate_kyc, prepare_user_edited_kyc
from app.providers import registry
from app.providers.base import UsageTrackingProvider
from app.services.guided_profile import KYC_PATCH_FIELDS, merge_kyc_patch


class BrandContextValidationError(Exception):
    """Caller-facing validation failure (422)."""


def _domain_from_url(url: str) -> str | None:
    host = (urlparse(url).hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _manual_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a KYC-shaped dict from create/patch fields."""

    profile: dict[str, Any] = {}
    brand = (payload.get("brand") or "").strip()
    if brand:
        profile["company"] = brand
    for key in KYC_PATCH_FIELDS:
        if key in payload and payload[key] is not None:
            profile[key] = payload[key]
    return profile


def get_org_brand_context(
    session: Session,
    *,
    org_id: uuid.UUID,
    context_id: uuid.UUID,
) -> BrandContext | None:
    return session.scalar(
        select(BrandContext).where(
            BrandContext.id == context_id,
            BrandContext.org_id == org_id,
        )
    )


def create_brand_context(
    session: Session,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict[str, Any],
    settings: Settings,
) -> BrandContext:
    source_url = (payload.get("source_url") or "").strip() or None
    locale = (payload.get("locale") or "en").strip() or "en"

    if source_url:
        if not is_public_url(source_url):
            raise BrandContextValidationError("url is not allowed")
        crawl = discovery.discover_detailed(source_url)
        provider = UsageTrackingProvider(registry.get_analysis_provider(settings))
        kyc = generate_kyc(crawl.text, source_url, provider)
        profile = kyc.model_dump()
        ctx = BrandContext(
            org_id=org_id,
            created_by_user_id=user_id,
            source_url=source_url,
            brand=kyc.company,
            domain=_domain_from_url(source_url),
            locale=locale,
            category=kyc.category or None,
            competitors=list(kyc.competitors or []),
            profile=profile,
        )
    else:
        brand = (payload.get("brand") or "").strip()
        if not brand:
            raise BrandContextValidationError("brand is required when source_url is omitted")
        profile_data = _manual_profile_payload(payload)
        kyc = KYC.model_validate({"company": brand, **profile_data})
        try:
            prepare_user_edited_kyc(kyc, url=payload.get("domain") or "")
        except PipelineError as exc:
            raise BrandContextValidationError(str(exc)) from exc
        ctx = BrandContext(
            org_id=org_id,
            created_by_user_id=user_id,
            source_url=source_url,
            brand=kyc.company,
            domain=(payload.get("domain") or None),
            locale=locale,
            category=kyc.category or None,
            competitors=list(kyc.competitors or []),
            profile=kyc.model_dump(),
        )

    session.add(ctx)
    session.flush()
    return ctx


def extract_brand_context_profile(
    session: Session,
    *,
    context: BrandContext,
    source_url: str,
    settings: Settings,
) -> BrandContext:
    """Discovery + KYC extract for an existing profile (mod-6 ``kyc_extract`` job)."""

    if not is_public_url(source_url):
        raise BrandContextValidationError("url is not allowed")
    crawl = discovery.discover_detailed(source_url)
    provider = UsageTrackingProvider(registry.get_analysis_provider(settings))
    kyc = generate_kyc(crawl.text, source_url, provider)
    context.source_url = source_url
    context.brand = kyc.company
    context.domain = _domain_from_url(source_url)
    context.category = kyc.category or None
    context.competitors = list(kyc.competitors or [])
    context.profile = kyc.model_dump()
    session.flush()
    return context


def patch_brand_context(
    session: Session,
    *,
    context: BrandContext,
    patch: dict[str, Any],
) -> BrandContext:
    unknown = set(patch) - (KYC_PATCH_FIELDS | {"brand", "domain", "locale", "category", "competitors"})
    if unknown:
        raise BrandContextValidationError(f"fields not allowed: {', '.join(sorted(unknown))}")

    profile_patch = {key: value for key, value in patch.items() if key in KYC_PATCH_FIELDS}
    if "brand" in patch and patch["brand"] is not None:
        profile_patch["company"] = patch["brand"]

    if profile_patch:
        merged = merge_kyc_patch(context.profile or {"company": context.brand}, profile_patch)
        try:
            prepare_user_edited_kyc(merged, url=context.source_url or "")
        except PipelineError as exc:
            raise BrandContextValidationError(str(exc)) from exc
        context.brand = merged.company
        context.category = merged.category or None
        context.competitors = list(merged.competitors or [])
        context.profile = merged.model_dump()

    if "domain" in patch:
        context.domain = patch["domain"]
    if "locale" in patch and patch["locale"] is not None:
        context.locale = patch["locale"]

    session.flush()
    return context
