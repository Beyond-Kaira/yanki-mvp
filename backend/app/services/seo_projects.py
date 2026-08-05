"""Persistence and domain normalization for user-owned SEO projects."""

from __future__ import annotations

import ipaddress
import re
import uuid
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import SeoProject, SiteAudit
from app.services.tenancy import OrgContext, create_project

_DNS_HOST_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.?$"
)
_ACTIVE_AUDIT_STATUSES = ("queued", "running")
AuditProfileId = Literal["site_audit_mobile", "site_audit_desktop"]


class InvalidProjectDomain(ValueError):
    pass


class DuplicateSeoProject(RuntimeError):
    pass


class SiteAuditAlreadyActive(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizedProjectDomain:
    url: str
    key: str
    default_name: str


def normalize_project_domain(raw_domain: str) -> NormalizedProjectDomain:
    """Turn a domain or URL into one root origin and a stable identity key."""

    value = raw_domain.strip()
    if not value:
        raise InvalidProjectDomain("domain is required")
    if "://" not in value:
        value = f"https://{value}"

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise InvalidProjectDomain("domain is not a valid HTTP or HTTPS URL") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise InvalidProjectDomain("domain is not a valid HTTP or HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidProjectDomain("domain must not include credentials")

    host = parsed.hostname.rstrip(".").lower()
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidProjectDomain("domain host is invalid") from exc

    try:
        ip = ipaddress.ip_address(ascii_host)
    except ValueError:
        if not _DNS_HOST_RE.fullmatch(ascii_host):
            raise InvalidProjectDomain("domain host is invalid")
        formatted_host = ascii_host
    else:
        formatted_host = f"[{ascii_host}]" if ip.version == 6 else ascii_host

    default_port = 443 if scheme == "https" else 80
    port_suffix = f":{port}" if port is not None and port != default_port else ""
    domain_url = urlunsplit((scheme, f"{formatted_host}{port_suffix}", "/", "", ""))

    identity_host = ascii_host[4:] if ascii_host.startswith("www.") else ascii_host
    domain_key = f"{identity_host}{port_suffix}"

    return NormalizedProjectDomain(
        url=domain_url,
        key=domain_key,
        default_name=identity_host,
    )


def create_project_with_audit(
    session: Session,
    *,
    user_id: uuid.UUID,
    domain: NormalizedProjectDomain,
    name: str | None,
    page_limit: int,
    profile_id: AuditProfileId,
    js_rendering: bool,
    context: OrgContext | None = None,
) -> SeoProject:
    """Create a Site Audit project and queue its first crawl.

    ``context`` is optional only so this stays callable from tests and from the
    pre-tenancy call path; when present — which is every HTTP request after
    P7.1 — the row is stamped with the caller's org/workspace and mirrored into
    a tenancy-level ``projects`` row, so Phase 8's backlink profiles have
    something to hang from.
    """

    existing_id = session.scalar(
        select(SeoProject.id).where(
            SeoProject.user_id == user_id,
            SeoProject.domain_key == domain.key,
        )
    )
    if existing_id is not None:
        raise DuplicateSeoProject

    project = SeoProject(
        user_id=user_id,
        name=name or domain.default_name,
        domain=domain.url,
        domain_key=domain.key,
    )
    if context is not None and context.org_id is not None:
        tracked = create_project(
            session,
            context=context,
            name=name or domain.default_name,
            domain=domain.url,
            domain_key=domain.key,
        )
        project.org_id = context.org_id
        project.workspace_id = tracked.workspace_id
        project.project_id = tracked.id
    audit = SiteAudit(
        project=project,
        page_limit=page_limit,
        profile_id=profile_id,
        js_rendering=js_rendering,
    )
    session.add_all([project, audit])

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateSeoProject from exc

    return project


def list_org_projects(session: Session, org_id: uuid.UUID) -> list[SeoProject]:
    """Every Site Audit project in one organization.

    Scoped by ``org_id``, not ``user_id``: a teammate must see the org's
    projects, and after P7.1 the org is the ownership boundary. Strict equality,
    so a missing or wrong org returns nothing rather than everything.
    """

    return list(
        session.scalars(
            select(SeoProject)
            .where(SeoProject.org_id == org_id)
            .options(selectinload(SeoProject.audits))
            .order_by(SeoProject.created_at.desc())
        )
    )


def get_org_project(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
) -> SeoProject | None:
    """One project, only if it belongs to this organization.

    A cross-org id resolves to None here and the route turns that into the same
    404 a nonexistent id gets — so the response cannot be used to probe whether
    another tenant's project exists.
    """

    return session.scalar(
        select(SeoProject)
        .where(
            SeoProject.id == project_id,
            SeoProject.org_id == org_id,
        )
        .options(selectinload(SeoProject.audits))
    )


def queue_site_audit(
    session: Session,
    *,
    project: SeoProject,
    page_limit: int,
    profile_id: AuditProfileId,
    js_rendering: bool,
) -> SiteAudit:
    active_id = session.scalar(
        select(SiteAudit.id).where(
            SiteAudit.project_id == project.id,
            SiteAudit.status.in_(_ACTIVE_AUDIT_STATUSES),
        )
    )
    if active_id is not None:
        raise SiteAuditAlreadyActive

    audit = SiteAudit(
        project_id=project.id,
        page_limit=page_limit,
        profile_id=profile_id,
        js_rendering=js_rendering,
    )
    session.add(audit)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise SiteAuditAlreadyActive from exc
    return audit


def get_org_audit(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    audit_id: uuid.UUID,
) -> SiteAudit | None:
    """One audit, scoped through the project that owns it.

    ``site_audits`` carries no ``org_id`` of its own — this join IS the scoping,
    which is why the child table needed no backfill.
    """

    return session.scalar(
        select(SiteAudit)
        .join(SeoProject, SeoProject.id == SiteAudit.project_id)
        .where(
            SiteAudit.id == audit_id,
            SiteAudit.project_id == project_id,
            SeoProject.org_id == org_id,
        )
        .options(selectinload(SiteAudit.pages))
    )
