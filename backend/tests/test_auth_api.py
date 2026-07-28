"""API tests for email/password signup and login."""

from sqlalchemy import func, select

from app.db.models import User
from app.services.auth import verify_password

SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"


def test_signup_creates_user_with_normalized_email_and_hashed_password(
    client,
    db_session,
) -> None:
    response = client.post(
        SIGNUP_URL,
        json={
            "email": "  Yakup@Example.COM  ",
            "password": "correct-horse",
        },
    )

    assert response.status_code == 201

    body = response.json()
    assert body["email"] == "yakup@example.com"
    assert set(body) == {"id", "email", "created_at"}

    user = db_session.scalar(select(User).where(User.email == "yakup@example.com"))

    assert user is not None
    assert user.password_hash != "correct-horse"
    assert verify_password("correct-horse", user.password_hash)


def test_signup_rejects_duplicate_normalized_email(
    client,
    db_session,
) -> None:
    first_response = client.post(
        SIGNUP_URL,
        json={
            "email": "yakup@example.com",
            "password": "correct-horse",
        },
    )
    duplicate_response = client.post(
        SIGNUP_URL,
        json={
            "email": " YAKUP@example.com ",
            "password": "another-password",
        },
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {"detail": "email already registered"}

    user_count = db_session.scalar(select(func.count()).select_from(User))
    assert user_count == 1


def test_login_accepts_valid_credentials(client) -> None:
    signup_response = client.post(
        SIGNUP_URL,
        json={
            "email": "yakup@example.com",
            "password": "correct-horse",
        },
    )
    assert signup_response.status_code == 201

    login_response = client.post(
        LOGIN_URL,
        json={
            "email": " YAKUP@EXAMPLE.COM ",
            "password": "correct-horse",
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["email"] == "yakup@example.com"
    assert set(login_response.json()) == {"id", "email", "created_at"}


def test_login_rejects_wrong_password_and_unknown_email(client) -> None:
    signup_response = client.post(
        SIGNUP_URL,
        json={
            "email": "yakup@example.com",
            "password": "correct-horse",
        },
    )
    assert signup_response.status_code == 201

    wrong_password_response = client.post(
        LOGIN_URL,
        json={
            "email": "yakup@example.com",
            "password": "wrong-password",
        },
    )
    unknown_email_response = client.post(
        LOGIN_URL,
        json={
            "email": "unknown@example.com",
            "password": "wrong-password",
        },
    )

    expected_error = {"detail": "invalid email or password"}

    assert wrong_password_response.status_code == 401
    assert wrong_password_response.json() == expected_error

    assert unknown_email_response.status_code == 401
    assert unknown_email_response.json() == expected_error


def test_auth_request_validation(client) -> None:
    invalid_email_response = client.post(
        SIGNUP_URL,
        json={
            "email": "not-an-email",
            "password": "correct-horse",
        },
    )
    short_password_response = client.post(
        SIGNUP_URL,
        json={
            "email": "yakup@example.com",
            "password": "short",
        },
    )
    empty_login_password_response = client.post(
        LOGIN_URL,
        json={
            "email": "yakup@example.com",
            "password": "",
        },
    )

    assert invalid_email_response.status_code == 422
    assert short_password_response.status_code == 422
    assert empty_login_password_response.status_code == 422
