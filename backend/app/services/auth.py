"""Authentication service helpers."""

import uuid
from datetime import UTC, datetime

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Membership, User
from app.services import audit
from app.services.tenancy import OrgContext, provision_org

_password_hash = PasswordHash.recommended()

_DUMMY_HASH = _password_hash.hash("dummy-password-for-timing-equalization")


def normalize_email(email: str) -> str:
    """Normalize an email before storing or querying it."""

    return email.strip().lower()


def hash_password(password: str) -> str:
    """Hash a plain-text password using the recommended password hasher."""

    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plain-text password against a stored password hash."""

    return _password_hash.verify(password, password_hash)


def verify_and_update_password(
    password: str,
    password_hash: str,
) -> tuple[bool, str | None]:
    """Verify a password and return an upgraded hash when needed."""
    return _password_hash.verify_and_update(password, password_hash)


def _audit_context(session: Session, user: User) -> OrgContext | None:
    """The organization an auth event belongs to, for the audit trail.

    Login and signup are the events an administrator most wants to see, and
    ``audit_events`` is queried **by organization**. An event written with a NULL
    org is therefore invisible in the Admin Panel's log — which is where these
    were, until this function existed: a sign-in trail nobody could read.

    Resolves the user's first active membership rather than calling
    ``resolve_org_context``, deliberately. That function provisions a personal
    org for a user who has none, and a *failed* login must not create anything.
    A user with no membership yields ``None`` and the event keeps a NULL org,
    which is the honest answer for an account that belongs to no tenant.
    """

    org_id: uuid.UUID | None = session.scalar(
        select(Membership.org_id)
        .where(Membership.user_id == user.id, Membership.status == "active")
        .order_by(Membership.created_at)
        .limit(1)
    )
    if org_id is None:
        return None
    return OrgContext(org_id=org_id, user_id=user.id)


def get_user_by_email(session: Session, email: str) -> User | None:
    """Return the user with the normalized email, if one exists."""

    normalized_email = normalize_email(email)

    return session.scalar(select(User).where(User.email == normalized_email))


def create_user(
    session: Session,
    *,
    email: str,
    password: str,
    account_type: str = "individual",
    organization_name: str | None = None,
) -> User:
    """Create and persist a user, with the personal organization that holds
    their data.

    The org is created in the **same transaction** as the user, deliberately.
    A user row with no organization is a state nothing downstream can serve —
    every scoped query needs an org context, and ``resolve_org_context`` raises
    without one — so a signup that produced one would be a half-registered
    account that fails on its first authenticated request. Committing both
    together means either the account exists and works, or it does not exist.
    """

    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
    )

    session.add(user)
    session.flush()
    org = provision_org(
        session,
        user,
        account_type=account_type,
        organization_name=organization_name,
    )
    # In the same transaction as the thing it describes, so a rolled-back
    # signup cannot leave an event claiming an account was created.
    audit.emit(
        session,
        action="auth:signup",
        # The org exists as of the line above, so the very first event in an
        # organization's life is already attributed to it.
        context=OrgContext(org_id=org.id, user_id=user.id),
        actor_type="user",
        actor_id=user.id,
        actor_label=user.email,
        entity_type="user",
        entity_id=user.id,
        after={
            "email": user.email,
            "account_type": account_type,
            "org_id": str(org.id),
            "org_slug": org.slug,
            "org_kind": org.kind,
        },
    )
    session.commit()
    session.refresh(user)

    return user


def authenticate_user(
    session: Session,
    *,
    email: str,
    password: str,
) -> User | None:
    """Return the user when the supplied credentials are valid."""

    user = get_user_by_email(session, email)

    password_hash = user.password_hash if user is not None else _DUMMY_HASH
    valid, updated_hash = verify_and_update_password(password, password_hash)

    if user is None or not valid:
        # A failed login is the event most worth having. Recorded with the
        # attempted address, never the attempted password.
        audit.emit(
            session,
            action="auth:login",
            # An unknown address belongs to no organization, so its failed login
            # keeps a NULL org. A KNOWN address's failure is attributed, because
            # "somebody is guessing at my colleague's password" is precisely the
            # event an administrator needs to find.
            context=_audit_context(session, user) if user is not None else None,
            actor_type="user" if user is not None else "anonymous",
            actor_id=user.id if user is not None else None,
            actor_label=normalize_email(email),
            entity_type="user",
            entity_id=user.id if user is not None else None,
            outcome="denied",
            detail={"reason": "invalid_credentials"},
        )
        session.commit()
        return None

    if user.status != "active":
        # Checked AFTER the password, deliberately: answering "this account is
        # disabled" to a wrong password would confirm the address exists.
        audit.emit(
            session,
            action="auth:login",
            context=_audit_context(session, user),
            actor_type="user",
            actor_id=user.id,
            actor_label=user.email,
            entity_type="user",
            entity_id=user.id,
            outcome="denied",
            detail={"reason": "account_disabled"},
        )
        session.commit()
        return None

    if updated_hash is not None:
        user.password_hash = updated_hash

    # The member list shows "last active", and until now the column was written
    # by nothing — every account read as having never signed in. A login is the
    # coarse-but-true signal; per-request touching would cost a write on every
    # authenticated call for a column nobody reads that precisely.
    user.last_active_at = datetime.now(UTC)

    audit.emit(
        session,
        action="auth:login",
        context=_audit_context(session, user),
        actor_type="user",
        actor_id=user.id,
        actor_label=user.email,
        entity_type="user",
        entity_id=user.id,
    )
    session.commit()

    return user
