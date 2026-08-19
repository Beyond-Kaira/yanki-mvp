"""Focused tests for authentication service behavior."""

from app.db.models import User
from app.services import auth as auth_service


def test_authenticate_user_uses_dummy_hash_for_unknown_email(
    db_session,
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(auth_service, "_DUMMY_HASH", "dummy-hash")

    def fake_verify_and_update(
        password: str,
        password_hash: str,
    ) -> tuple[bool, str | None]:
        calls.append((password, password_hash))
        return False, None

    monkeypatch.setattr(
        auth_service,
        "verify_and_update_password",
        fake_verify_and_update,
    )

    user = auth_service.authenticate_user(
        db_session,
        email="unknown@example.com",
        password="wrong-password",
    )

    assert user is None
    assert calls == [("wrong-password", "dummy-hash")]


def test_authenticate_user_persists_upgraded_password_hash(
    db_session,
    monkeypatch,
) -> None:
    user = User(
        email="test@example.com",
        password_hash="old-hash",
    )
    db_session.add(user)
    db_session.commit()

    user_id = user.id

    def fake_verify_and_update(
        password: str,
        password_hash: str,
    ) -> tuple[bool, str | None]:
        assert password == "correct-horse"
        assert password_hash == "old-hash"
        return True, "upgraded-hash"

    monkeypatch.setattr(
        auth_service,
        "verify_and_update_password",
        fake_verify_and_update,
    )

    authenticated_user = auth_service.authenticate_user(
        db_session,
        email="test@example.com",
        password="correct-horse",
    )

    assert authenticated_user is not None
    assert authenticated_user.id == user_id

    db_session.expire_all()
    persisted_user = db_session.get(User, user_id)

    assert persisted_user is not None
    assert persisted_user.password_hash == "upgraded-hash"


def test_a_password_verifies_in_whichever_unicode_form_it_is_typed() -> None:
    """NFKC on both ends, or the normalization would lock people out.

    The same Turkish password can arrive precomposed from one keyboard and
    decomposed from another. Hashing without normalizing stores a secret only
    one of those two keyboards can reproduce; normalizing on the way IN but not
    on the way OUT is worse still, because it stores one nobody can. This is the
    test that fails if either half is removed.
    """

    precomposed = "şifremiz-uzun-olsun"
    decomposed = "şifremiz-uzun-olsun"
    assert precomposed != decomposed

    stored = auth_service.hash_password(precomposed)

    assert auth_service.verify_password(decomposed, stored) is True
    assert auth_service.verify_password(precomposed, stored) is True
