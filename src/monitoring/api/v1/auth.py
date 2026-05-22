from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from monitoring.dependencies import CurrentUser, DbSession
from monitoring.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from monitoring.services.auth_service import AuthService
from monitoring.services.rate_limit_service import clear_rate_limit, is_rate_limited, rate_limit_key

router = APIRouter()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: DbSession) -> RegisterResponse:
    service = AuthService(db)
    try:
        user = await service.register(data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return RegisterResponse(
        user=UserResponse.model_validate(user),
        message="Verification code sent. Check your email before logging in.",
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: DbSession) -> TokenResponse:
    key = rate_limit_key("login", data.email)
    if is_rate_limited(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")
    service = AuthService(db)
    user = await service.authenticate(data.email, data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    clear_rate_limit(key)
    return await service.create_token_response(user)


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(data: VerifyEmailRequest, db: DbSession) -> UserResponse:
    key = rate_limit_key("verify-email", data.email)
    if is_rate_limited(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")
    user = await AuthService(db).verify_email(data.email, data.code)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )
    clear_rate_limit(key)
    return UserResponse.model_validate(user)


@router.post("/resend-verification", response_model=RegisterResponse)
async def resend_verification(
    data: ResendVerificationRequest,
    db: DbSession,
) -> RegisterResponse:
    key = rate_limit_key("resend-verification", data.email)
    if is_rate_limited(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")
    try:
        user = await AuthService(db).resend_verification_code(data.email)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    message = (
        "Email is already verified."
        if user.is_verified
        else "Verification code sent. Check your email before logging in."
    )
    clear_rate_limit(key)
    return RegisterResponse(user=UserResponse.model_validate(user), message=message)


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, db: DbSession) -> dict[str, str]:
    key = rate_limit_key("forgot-password", data.email)
    if is_rate_limited(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")
    try:
        await AuthService(db).request_password_reset(data.email)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {"message": "If the email exists, a password reset code has been sent."}


@router.post("/reset-password", response_model=UserResponse)
async def reset_password(data: ResetPasswordRequest, db: DbSession) -> UserResponse:
    key = rate_limit_key("reset-password", data.email)
    if is_rate_limited(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")
    user = await AuthService(db).reset_password(data.email, data.code, data.new_password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset code",
        )
    clear_rate_limit(key)
    return UserResponse.model_validate(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshTokenRequest, db: DbSession) -> TokenResponse:
    token = await AuthService(db).refresh_access_token(data.refresh_token)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    return token


@router.post("/logout")
async def logout(data: LogoutRequest, db: DbSession) -> dict[str, str]:
    await AuthService(db).revoke_refresh_token(data.refresh_token)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
