"""The personal-org backfill — the repo's first data migration (P7.1).

It lives here rather than inside ``alembic/versions/0012_tenancy.py`` for one
reason: **it has to be testable.** A backfill buried in a migration can only be
exercised by running Alembic against Postgres, which in practice means it is
exercised once, by hand, against a database nobody minds breaking. Here it is an
ordinary function taking a connection, so the SQLite suite runs it against
fixtures nastier than production — colliding local-parts, an unslugifiable
email, a re-run — and the migration is a one-line caller.

That constraint shapes the implementation. The tables are declared as **Core
constructs against a private MetaData**, deliberately not the ORM models:

* Typed. A ``sa.Uuid`` column binds correctly on SQLite *and* Postgres. Raw
  ``sa.text()`` carries no type information, so a UUID parameter reaches
  SQLite's driver unconverted and raises — while Postgres happens to tolerate
  it. That asymmetry is how an engine-specific bug reaches production
  unnoticed; the SQLite tests here caught this one before it was committed.
* Frozen. A migration must keep describing the schema *as it was when written*.
  Importing the ORM models would mean a column added by some later card changes
  what this migration does to a year-old database — the classic way an old
  migration starts failing on a fresh checkout.

Idempotent throughout. A retried deploy, a rollback-and-forward, or the signup
resolver's get-or-create racing the migration all converge instead of minting a
second home for anybody.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.engine import Connection

# The reserved organization that owns the public surface. A fixed UUID rather
# than a generated one, so it is the same row in every environment and can be
# referenced from code, fixtures and SQL without a lookup.
#
# It makes the mapping *total*: the acceptance criterion asks that every
# pre-existing row be reachable through exactly one organization, and anonymous
# rows carry NULL. NULL is defined as "the public scope"; this row is what that
# scope names. Anonymous rows are never rewritten to point at it — that would
# mass-write the hot table for no functional gain, and would make public rows
# *look* owned, which is the one thing tenant isolation must never produce.
PUBLIC_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PUBLIC_ORG_SLUG = "public"

DEFAULT_WORKSPACE_NAME = "Default"
DEFAULT_WORKSPACE_SLUG = "default"
ROLE_OWNER = "owner"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LENGTH = 40

# Slugs a tenant may never take: they name the public org or read as first-party
# routes. Seeded into the "used" set so the ordinary suffixing rule steers
# around them with no special case.
RESERVED_SLUGS = frozenset(
    {PUBLIC_ORG_SLUG, "admin", "api", "app", "system", "yanki", "www", "static"}
)

# A private MetaData — see the module docstring. These describe only the columns
# the backfill touches, as of migration 0012.
_meta = sa.MetaData()

_users = sa.Table(
    "users",
    _meta,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("email", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

_organizations = sa.Table(
    "organizations",
    _meta,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("name", sa.Text),
    sa.Column("slug", sa.Text),
    sa.Column("kind", sa.Text),
    sa.Column("status", sa.Text),
    sa.Column("owner_user_id", sa.Uuid),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

_workspaces = sa.Table(
    "workspaces",
    _meta,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("org_id", sa.Uuid),
    sa.Column("name", sa.Text),
    sa.Column("slug", sa.Text),
    sa.Column("is_default", sa.Boolean),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

_memberships = sa.Table(
    "memberships",
    _meta,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("org_id", sa.Uuid),
    sa.Column("user_id", sa.Uuid),
    sa.Column("role", sa.Text),
    sa.Column("status", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

_projects = sa.Table(
    "projects",
    _meta,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("org_id", sa.Uuid),
    sa.Column("workspace_id", sa.Uuid),
    sa.Column("name", sa.Text),
    sa.Column("domain", sa.Text),
    sa.Column("domain_key", sa.Text),
    sa.Column("locale", sa.Text),
    sa.Column("status", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

_seo_projects = sa.Table(
    "seo_projects",
    _meta,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("user_id", sa.Uuid),
    sa.Column("org_id", sa.Uuid),
    sa.Column("workspace_id", sa.Uuid),
    sa.Column("project_id", sa.Uuid),
    sa.Column("name", sa.Text),
    sa.Column("domain", sa.Text),
    sa.Column("domain_key", sa.Text),
)


def _now() -> datetime:
    """Timestamps written explicitly, not left to a default.

    The ORM models default ``created_at`` in *Python*, so ``create_all`` gives
    SQLite a NOT NULL column with no server default; the Alembic migration gives
    Postgres ``now()``. A Core insert therefore succeeds on Postgres and fails on
    SQLite — another asymmetry the SQLite tests caught. Supplying the value
    removes the dependency on either.
    """

    return datetime.now(UTC)


def slugify(value: str) -> str:
    """Lowercase, ``[a-z0-9-]`` only, collapsed, trimmed to 40 characters.

    Returns ``""`` when nothing survives. An all-punctuation or non-Latin local
    part is a real input, and callers pick the fallback rather than having one
    silently substituted here.
    """

    return _SLUG_STRIP.sub("-", (value or "").strip().lower()).strip("-")[:_MAX_SLUG_LENGTH]


def unique_slug(base: str, used: set[str]) -> str:
    """First free of ``base``, ``base-2``, ``base-3``, … recording the winner.

    ``used`` is authoritative and is mutated, which makes the backfill
    collision-proof *by construction* rather than by hope: the loop cannot
    terminate on a value already in the set, so ``uq_organizations_slug`` cannot
    be violated whatever the email column happens to contain.
    """

    root = base or "org"
    candidate = root
    suffix = 1
    while candidate in used:
        suffix += 1
        candidate = f"{root}-{suffix}"
    used.add(candidate)
    return candidate


def backfill_orgs(connection: Connection) -> None:
    """Give every existing user a home, and every owned row an organization.

    Order matters: the public org first, so it exists whatever follows; then one
    personal org + default workspace + owner membership per user; then one
    tracked-business ``projects`` row per ``seo_projects`` row, with the links
    stamped back.

    ``analyses`` is deliberately untouched — every row is anonymous and stays
    that way. See the module docstring and ADR-35.
    """

    _ensure_public_org(connection)

    users = connection.execute(
        sa.select(_users.c.id, _users.c.email).order_by(_users.c.created_at, _users.c.id)
    ).fetchall()
    if not users:
        return

    used = {row[0] for row in connection.execute(sa.select(_organizations.c.slug))} | set(
        RESERVED_SLUGS
    )

    homes: dict[uuid.UUID, tuple[uuid.UUID, uuid.UUID]] = {}
    for user_id, email in users:
        homes[user_id] = _ensure_personal_home(connection, user_id, email or "", used)

    _link_seo_projects(connection, homes)


def _ensure_public_org(connection: Connection) -> None:
    exists = connection.execute(
        sa.select(_organizations.c.id).where(_organizations.c.id == PUBLIC_ORG_ID)
    ).fetchone()
    if exists is not None:
        return
    connection.execute(
        sa.insert(_organizations).values(
            id=PUBLIC_ORG_ID,
            name="Public",
            slug=PUBLIC_ORG_SLUG,
            kind="system",
            status="active",
            owner_user_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
    )


def _ensure_personal_home(
    connection: Connection,
    user_id: uuid.UUID,
    email: str,
    used: set[str],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Return ``(org_id, workspace_id)`` for one user, creating what is missing."""

    existing = connection.execute(
        sa.select(_organizations.c.id)
        .where(
            _organizations.c.owner_user_id == user_id,
            _organizations.c.kind == "personal",
        )
        .order_by(_organizations.c.created_at, _organizations.c.id)
        .limit(1)
    ).fetchone()

    if existing is not None:
        org_id = existing[0]
    else:
        org_id = uuid.uuid4()
        local_part = email.split("@", 1)[0] or "account"
        connection.execute(
            sa.insert(_organizations).values(
                id=org_id,
                name=f"{local_part}'s organization",
                slug=unique_slug(slugify(local_part), used),
                kind="personal",
                status="active",
                owner_user_id=user_id,
                created_at=_now(),
                updated_at=_now(),
            )
        )

    workspace = connection.execute(
        sa.select(_workspaces.c.id)
        .where(_workspaces.c.org_id == org_id)
        .order_by(_workspaces.c.created_at, _workspaces.c.id)
        .limit(1)
    ).fetchone()

    if workspace is not None:
        workspace_id = workspace[0]
    else:
        workspace_id = uuid.uuid4()
        connection.execute(
            sa.insert(_workspaces).values(
                id=workspace_id,
                org_id=org_id,
                name=DEFAULT_WORKSPACE_NAME,
                slug=DEFAULT_WORKSPACE_SLUG,
                is_default=True,
                created_at=_now(),
                updated_at=_now(),
            )
        )

    membership = connection.execute(
        sa.select(_memberships.c.id).where(
            _memberships.c.org_id == org_id, _memberships.c.user_id == user_id
        )
    ).fetchone()
    if membership is None:
        connection.execute(
            sa.insert(_memberships).values(
                id=uuid.uuid4(),
                org_id=org_id,
                user_id=user_id,
                role=ROLE_OWNER,
                status="active",
                created_at=_now(),
                updated_at=_now(),
            )
        )

    return org_id, workspace_id


def _link_seo_projects(
    connection: Connection,
    homes: dict[uuid.UUID, tuple[uuid.UUID, uuid.UUID]],
) -> None:
    rows = connection.execute(
        sa.select(
            _seo_projects.c.id,
            _seo_projects.c.user_id,
            _seo_projects.c.name,
            _seo_projects.c.domain,
            _seo_projects.c.domain_key,
        ).where(_seo_projects.c.project_id.is_(None))
    ).fetchall()

    for sp_id, user_id, name, domain, domain_key in rows:
        home = homes.get(user_id)
        if home is None:
            # The FK cascade makes an orphan impossible — but a data migration
            # that assumes its way into a KeyError takes the release down with
            # it, and this costs one branch.
            continue
        org_id, workspace_id = home

        existing = connection.execute(
            sa.select(_projects.c.id).where(
                _projects.c.org_id == org_id, _projects.c.domain_key == domain_key
            )
        ).fetchone()

        if existing is not None:
            project_id = existing[0]
        else:
            project_id = uuid.uuid4()
            connection.execute(
                sa.insert(_projects).values(
                    id=project_id,
                    org_id=org_id,
                    workspace_id=workspace_id,
                    name=name,
                    domain=domain,
                    domain_key=domain_key,
                    locale="en",
                    status="active",
                    created_at=_now(),
                    updated_at=_now(),
                )
            )

        connection.execute(
            sa.update(_seo_projects)
            .where(_seo_projects.c.id == sp_id)
            .values(org_id=org_id, workspace_id=workspace_id, project_id=project_id)
        )
