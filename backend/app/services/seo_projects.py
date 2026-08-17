"""Persistence and domain normalization for user-owned SEO projects."""

from __future__ import annotations

import ipaddress
import re
import uuid
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import Project, SeoProject, SiteAudit
from app.services import audit as audit_service
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


def already_tracked(session: Session, *, user_id: uuid.UUID, domain_key: str) -> bool:
    """Whether this user already tracks this domain.

    Extracted so the route can ask *before* it spends a quota. A duplicate
    submission and an exhausted plan both refuse the request, but they are not
    the same answer: "you already track this" is a 409 the customer fixes by
    opening the project they have, while a 429 tells them to buy something they
    do not need. Checking the cheaper, more specific one first is what keeps the
    order of guards from changing what the customer is told.

    ``create_project_with_audit`` keeps its own copy of the check — this is a
    pre-check, not a replacement, and the unique constraint underneath is the
    actual guarantee.
    """

    return (
        session.scalar(
            select(SeoProject.id).where(
                SeoProject.user_id == user_id,
                SeoProject.domain_key == domain_key,
            )
        )
        is not None
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
    queue_audit: bool = True,
) -> SeoProject:
    """Create an SEO project and, unless suppressed, queue its first crawl.

    ``context`` is optional only so this stays callable from tests and from the
    pre-tenancy call path; when present — which is every HTTP request after
    P7.1 — the row is stamped with the caller's org/workspace and mirrored into
    a tenancy-level ``projects`` row, so Phase 8's backlink profiles have
    something to hang from.

    ``queue_audit`` defaults to True, so every existing caller and test keeps
    its behaviour. When False, the project and its tenancy ``projects`` mirror
    are still created — the shared project entity that Backlinks hangs off must
    exist regardless — but **no** ``SiteAudit`` row is enqueued. The enqueue
    routes pass ``settings.site_audit_enabled`` here so project creation stays
    open while the site-audit queue has no worker to drain it; an audit is only
    ever queued once the feature is switched on. See ``config.site_audit_enabled``.
    """

    if already_tracked(session, user_id=user_id, domain_key=domain.key):
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
    session.add(project)
    if queue_audit:
        audit = SiteAudit(
            project=project,
            page_limit=page_limit,
            profile_id=profile_id,
            js_rendering=js_rendering,
        )
        session.add(audit)

    audit_service.emit(
        session,
        action="project:create",
        context=context,
        actor_type="user",
        actor_id=user_id,
        entity_type="seo_project",
        entity_id=project.id,
        after={
            "name": project.name,
            "domain": project.domain,
            "domain_key": project.domain_key,
        },
    )

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


def count_org_projects(session: Session, org_id: uuid.UUID) -> int:
    """How many Site Audit projects this organization currently holds.

    The plan's ``projects`` allowance is a stock, not a monthly flow, so the
    quota check compares against the rows that exist rather than a counter —
    see ``billing.check_stock_quota``. Counting ``SeoProject`` rather than the
    tenancy mirror ``Project`` is deliberate: ``SeoProject`` is the thing a
    customer creates and sees, and the two are written together.
    """

    return int(
        session.scalar(
            select(func.count()).select_from(SeoProject).where(SeoProject.org_id == org_id)
        )
        or 0
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


def delete_project(
    session: Session,
    *,
    project: SeoProject,
    context: OrgContext | None = None,
) -> None:
    """Stop tracking a domain, and remove everything recorded against it.

    **Both** rows go: the ``seo_projects`` row the customer sees, and the
    tenancy ``projects`` mirror it was created with. Deleting only the first
    looks tidier and is wrong twice over:

    * ``projects`` carries ``uq_projects_org_domain_key``, so the orphan would
      collide the next time the same domain was added — and the collision
      surfaces as ``DuplicateSeoProject``, which the route reports as "an SEO
      project for this domain already exists". The customer would be told a
      project exists that they had just deleted and cannot see.
    * Everything hanging off ``projects`` — the backlink profile, its imports,
      link events and rollups — is reachable only through
      ``/seo-projects/{id}/backlinks``, which resolves the ``seo_projects`` row
      first. Without its mirror those rows are unreadable and undeletable, so
      "keeping" them preserves nothing and leaks storage.

    The two are written together in :func:`create_project_with_audit`; they are
    removed together here for the same reason. Audits and crawled pages follow
    by cascade (ORM relationship *and* ``ON DELETE CASCADE``).

    Deliberately **not** guarded on an active crawl. A queued or running audit
    can be deleted, and the worker tolerates it: the in-flight run fails on the
    vanished rows, rolls back, and ``worker.run_once`` finds no audit to mark
    failed, logs, and moves on. The alternative — refusing while an audit is
    ``queued`` — would mean a job nobody drains (which is the state of every
    deployment with ``SITE_AUDIT_ENABLED=0``) pins a project in the list
    permanently. Losing one crawl's work is the cheaper failure.

    The project allowance is a stock counted from the rows that exist
    (:func:`count_org_projects`), so deleting one frees a slot with no counter
    to decrement.
    """

    tracked_project_id = project.project_id

    audit_service.emit(
        session,
        action="project:delete",
        context=context,
        actor_type="user",
        actor_id=project.user_id,
        entity_type="seo_project",
        entity_id=project.id,
        before={
            "name": project.name,
            "domain": project.domain,
            "domain_key": project.domain_key,
        },
        after=None,
    )

    session.delete(project)
    if tracked_project_id is not None:
        tracked = session.get(Project, tracked_project_id)
        if tracked is not None:
            session.delete(tracked)
    session.commit()


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

    site_audit = SiteAudit(
        project_id=project.id,
        page_limit=page_limit,
        profile_id=profile_id,
        js_rendering=js_rendering,
    )
    session.add(site_audit)
    session.flush()
    audit_service.emit(
        session,
        action="site_audit:queue",
        actor_type="user",
        actor_id=project.user_id,
        entity_type="site_audit",
        entity_id=site_audit.id,
        after={
            "project_id": str(project.id),
            "page_limit": page_limit,
            "profile_id": profile_id,
            "js_rendering": js_rendering,
        },
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise SiteAuditAlreadyActive from exc
    return site_audit


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
