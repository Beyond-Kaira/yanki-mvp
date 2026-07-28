"""Authentication service helpers."""

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User

_password_hash = PasswordHash.recommended()


def normalize_email(email: str) -> str:
    """Normalize an email before storing or querying it."""

    return email.strip().lower()


def hash_password(password: str) -> str:
    """Hash a plain-text password using the recommended password hasher."""

    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plain-text password against a stored password hash."""

    return _password_hash.verify(password, password_hash)


def get_user_by_email(session: Session, email: str) -> User | None:
    """Return the user with the normalized email, if one exists."""

    normalized_email = normalize_email(email)

    return session.scalar(select(User).where(User.email == normalized_email))


def create_user(
    session: Session,
    *,
    email: str,
    password: str,
) -> User:
    """Create and persist a user with a hashed password."""

    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
    )

    session.add(user)
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

    if user is None:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user
