"""HTTP routes for email/password authentication."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import LoginRequest, LoginResponse, SignupRequest, UserOut
from app.db.session import get_session
from app.services.auth import authenticate_user, create_user, get_user_by_email

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
)
def signup(
    payload: SignupRequest,
    session: Session = Depends(get_session),
) -> UserOut:
    """Create a user account with a hashed password."""

    if get_user_by_email(session, payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already registered",
        )

    try:
        user = create_user(
            session,
            email=payload.email,
            password=payload.password,
        )
    except IntegrityError as exc:
        # Handles the race where two requests try to register the same email
        # between the lookup above and the database insert.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already registered",
        ) from exc

    return UserOut.model_validate(user)


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(
    payload: LoginRequest,
    session: Session = Depends(get_session),
) -> LoginResponse:
    """Validate a user's email and password."""

    user = authenticate_user(
        session,
        email=payload.email,
        password=payload.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
        )

    return LoginResponse(
        user=UserOut.model_validate(user),
    )
