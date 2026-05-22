from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.alerting.transactional_email import TransactionalEmailSender
from monitoring.config import get_settings
from monitoring.core.security import (
    create_access_token,
    hash_email_verification_code,
    hash_opaque_token,
    hash_password,
    hash_password_reset_code,
    new_opaque_token,
    verify_email_verification_code,
    verify_password,
    verify_password_reset_code,
)
from monitoring.models.user import AuthSession, User
from monitoring.schemas.auth import RegisterRequest, TokenResponse, UserResponse

settings = get_settings()


class AuthService:
    """Registration and login behavior."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_public_id(self, public_id: str) -> User | None:
        try:
            parsed_id = uuid.UUID(public_id)
        except ValueError:
            return None
        stmt = select(User).where(User.public_id == parsed_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def register(self, data: RegisterRequest) -> User:
        existing = await self.get_user_by_email(data.email)
        if existing is not None:
            raise ValueError("Email is already registered")

        user = User(
            full_name=data.full_name,
            email=data.email.lower(),
            password_hash=hash_password(data.password),
        )
        code = self._new_verification_code()
        self._set_verification_code(user, code)
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        if not await self._send_verification_email(user, code):
            raise RuntimeError("Verification email could not be sent")
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.get_user_by_email(email)
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    async def resend_verification_code(self, email: str) -> User | None:
        user = await self.get_user_by_email(email)
        if user is None or not user.is_active:
            return None
        if user.is_verified:
            return user
        code = self._new_verification_code()
        self._set_verification_code(user, code)
        await self.db.flush()
        await self.db.refresh(user)
        if not await self._send_verification_email(user, code):
            raise RuntimeError("Verification email could not be sent")
        return user

    async def verify_email(self, email: str, code: str) -> User | None:
        user = await self.get_user_by_email(email)
        if user is None or not user.is_active:
            return None
        if user.is_verified:
            return user
        expires_at = user.email_verification_expires_at
        if expires_at is None:
            return None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            return None
        if user.email_verification_failed_attempts >= settings.max_verification_attempts:
            return None
        if not verify_email_verification_code(user.email, code, user.email_verification_code_hash):
            user.email_verification_failed_attempts += 1
            await self.db.flush()
            return None

        user.is_verified = True
        user.verified_at = datetime.now(UTC)
        user.email_verification_code_hash = None
        user.email_verification_expires_at = None
        user.email_verification_failed_attempts = 0
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def create_token_response(self, user: User) -> TokenResponse:
        refresh_token = await self.create_refresh_session(user)
        return TokenResponse(
            access_token=create_access_token(str(user.public_id)),
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        )

    async def create_refresh_session(self, user: User) -> str:
        token = new_opaque_token()
        session = AuthSession(
            token_hash=hash_opaque_token(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
        self.db.add(session)
        await self.db.flush()
        return token

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse | None:
        session = await self._get_active_refresh_session(refresh_token)
        if session is None:
            return None
        user = await self.db.get(User, session.user_id)
        if user is None or not user.is_active or not user.is_verified:
            return None
        return TokenResponse(
            access_token=create_access_token(str(user.public_id)),
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        )

    async def revoke_refresh_token(self, refresh_token: str) -> bool:
        session = await self._get_active_refresh_session(refresh_token)
        if session is None:
            return False
        session.revoked_at = datetime.now(UTC)
        await self.db.flush()
        return True

    async def request_password_reset(self, email: str) -> User | None:
        user = await self.get_user_by_email(email)
        if user is None or not user.is_active:
            return None
        code = self._new_verification_code()
        user.password_reset_code_hash = hash_password_reset_code(user.email, code)
        user.password_reset_expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.password_reset_code_expire_minutes,
        )
        user.password_reset_failed_attempts = 0
        await self.db.flush()
        await self.db.refresh(user)
        if not await self._send_password_reset_email(user, code):
            raise RuntimeError("Password reset email could not be sent")
        return user

    async def reset_password(self, email: str, code: str, new_password: str) -> User | None:
        user = await self.get_user_by_email(email)
        if user is None or not user.is_active:
            return None
        expires_at = user.password_reset_expires_at
        if expires_at is None:
            return None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            return None
        if user.password_reset_failed_attempts >= settings.max_verification_attempts:
            return None
        if not verify_password_reset_code(user.email, code, user.password_reset_code_hash):
            user.password_reset_failed_attempts += 1
            await self.db.flush()
            return None
        user.password_hash = hash_password(new_password)
        user.password_reset_code_hash = None
        user.password_reset_expires_at = None
        user.password_reset_failed_attempts = 0
        user.is_verified = True
        user.verified_at = user.verified_at or datetime.now(UTC)
        await self._revoke_user_sessions(user.id)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    def _set_verification_code(self, user: User, code: str) -> None:
        user.email_verification_code_hash = hash_email_verification_code(user.email, code)
        user.email_verification_expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.email_verification_code_expire_minutes,
        )
        user.email_verification_failed_attempts = 0

    @staticmethod
    def _new_verification_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    async def _send_verification_email(self, user: User, code: str) -> bool:
        if not settings.email_enabled:
            return False
        return await TransactionalEmailSender(settings).send_verification_code(
            to_email=user.email,
            code=code,
            expires_minutes=settings.email_verification_code_expire_minutes,
        )

    async def _send_password_reset_email(self, user: User, code: str) -> bool:
        if not settings.email_enabled:
            return False
        return await TransactionalEmailSender(settings).send_password_reset_code(
            to_email=user.email,
            code=code,
            expires_minutes=settings.password_reset_code_expire_minutes,
        )

    async def _get_active_refresh_session(self, refresh_token: str) -> AuthSession | None:
        stmt = select(AuthSession).where(AuthSession.token_hash == hash_opaque_token(refresh_token))
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if session is None or session.revoked_at is not None:
            return None
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            return None
        return session

    async def _revoke_user_sessions(self, user_id: int) -> None:
        result = await self.db.execute(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        for session in result.scalars().all():
            session.revoked_at = datetime.now(UTC)
