from fastapi import APIRouter, HTTPException, status

from app.api.deps import AppSettings, CurrentUser, DbSession, ResetNotifier
from app.api.responses import errors
from app.core import security
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserRead,
)
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses=errors(409),
)
def signup(data: SignupRequest, db: DbSession) -> UserRead:
    try:
        return auth_service.signup(db, data)
    except auth_service.DuplicateUserError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.post("/login", response_model=TokenResponse, responses=errors(401))
def login(data: LoginRequest, db: DbSession, settings: AppSettings) -> TokenResponse:
    user = auth_service.authenticate(db, data.identifier, data.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=security.create_access_token(settings, user.id),
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead, responses=errors(401))
def me(current_user: CurrentUser) -> UserRead:
    return current_user


@router.post(
    "/forgot-password", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED
)
def forgot_password(
    data: ForgotPasswordRequest,
    db: DbSession,
    settings: AppSettings,
    notify: ResetNotifier,
) -> MessageResponse:
    user = auth_service.get_user_by_email(db, data.email)
    if user is not None:
        token = security.create_reset_token(settings, user.id, user.password_hash)
        notify(settings, user.email, token)
    # Same response whether or not the email exists (no account enumeration).
    return MessageResponse(message="If the email is registered, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse, responses=errors(400))
def reset_password(
    data: ResetPasswordRequest, db: DbSession, settings: AppSettings
) -> MessageResponse:
    if not auth_service.reset_password(db, settings, data.token, data.new_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")
    return MessageResponse(message="Password updated.")
