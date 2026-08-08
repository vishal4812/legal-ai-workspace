from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.auth import get_refresh_token_by_jti, get_user_by_email, get_user_by_id
from app.schemas.auth import LoginRequest, RegistrationRequest
from app.security.exceptions import AuthenticationError, DuplicateEmailError, InactiveUserError
from app.security.passwords import consume_password_verification_time, hash_password, verify_password
from app.security.tokens import DecodedToken, InvalidTokenError, TokenManager, TokenPair, TokenType


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class AuthService:
    """Coordinates authentication use cases and refresh-session rotation."""

    def __init__(self, session: AsyncSession, tokens: TokenManager) -> None:
        self._session = session
        self._tokens = tokens

    async def register(self, request: RegistrationRequest) -> User:
        if await get_user_by_email(self._session, str(request.email)):
            raise DuplicateEmailError

        user = User(
            email=str(request.email),
            password_hash=hash_password(request.password),
            first_name=request.first_name,
            last_name=request.last_name,
        )
        self._session.add(user)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateEmailError from exc
        await self._session.refresh(user)
        return user

    async def login(self, request: LoginRequest) -> TokenPair:
        user = await get_user_by_email(self._session, str(request.email))
        if user is None:
            consume_password_verification_time(request.password)
            raise AuthenticationError
        if not verify_password(request.password, user.password_hash):
            raise AuthenticationError
        if not user.is_active:
            raise InactiveUserError

        now = datetime.now(UTC)
        user.last_login_at = now
        pair = self._tokens.create_pair(user.id)
        self._session.add(self._new_refresh_session(user, pair))
        await self._session.commit()
        return pair

    async def refresh(self, raw_token: str) -> TokenPair:
        decoded = self._decode_refresh(raw_token)
        record = await get_refresh_token_by_jti(self._session, decoded.jti, for_update=True)
        now = datetime.now(UTC)
        if (
            record is None
            or record.user_id != decoded.subject
            or record.revoked_at is not None
            or as_utc(record.expires_at) <= now
        ):
            raise AuthenticationError

        user = await get_user_by_id(self._session, decoded.subject)
        if user is None:
            raise AuthenticationError
        if not user.is_active:
            raise InactiveUserError

        record.revoked_at = now
        record.last_used_at = now
        pair = self._tokens.create_pair(user.id)
        self._session.add(self._new_refresh_session(user, pair))
        await self._session.commit()
        return pair

    async def logout(self, raw_token: str) -> None:
        decoded = self._decode_refresh(raw_token)
        record = await get_refresh_token_by_jti(self._session, decoded.jti, for_update=True)
        now = datetime.now(UTC)
        if (
            record is None
            or record.user_id != decoded.subject
            or record.revoked_at is not None
            or as_utc(record.expires_at) <= now
        ):
            raise AuthenticationError
        record.revoked_at = now
        record.last_used_at = now
        await self._session.commit()

    def _decode_refresh(self, raw_token: str) -> DecodedToken:
        try:
            return self._tokens.decode(raw_token, TokenType.REFRESH)
        except InvalidTokenError as exc:
            raise AuthenticationError from exc

    @staticmethod
    def _new_refresh_session(user: User, pair: TokenPair) -> RefreshToken:
        return RefreshToken(
            user_id=user.id,
            token_jti=pair.refresh_jti,
            expires_at=pair.refresh_expires_at,
        )
