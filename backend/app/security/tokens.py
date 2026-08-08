from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

import jwt

from app.config import Settings


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DecodedToken:
    subject: UUID
    token_type: TokenType
    jti: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    refresh_jti: str
    refresh_expires_at: datetime
    access_expires_in: int


class TokenManager:
    """Create and strictly validate signed access and refresh JWTs."""

    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret.get_secret_value()
        self._algorithm = settings.jwt_algorithm
        self._access_lifetime = timedelta(minutes=settings.jwt_access_token_expire_minutes)
        self._refresh_lifetime = timedelta(days=settings.jwt_refresh_token_expire_days)

    def create_pair(self, subject: UUID) -> TokenPair:
        access_token, _, _ = self.create_token(subject, TokenType.ACCESS, self._access_lifetime)
        refresh_token, refresh_jti, refresh_expires_at = self.create_token(
            subject,
            TokenType.REFRESH,
            self._refresh_lifetime,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            refresh_jti=refresh_jti,
            refresh_expires_at=refresh_expires_at,
            access_expires_in=int(self._access_lifetime.total_seconds()),
        )

    def create_token(
        self,
        subject: UUID,
        token_type: TokenType,
        lifetime: timedelta,
    ) -> tuple[str, str, datetime]:
        issued_at = datetime.now(UTC)
        expires_at = issued_at + lifetime
        jti = str(uuid4())
        token = jwt.encode(
            {
                "sub": str(subject),
                "type": token_type.value,
                "iat": issued_at,
                "exp": expires_at,
                "jti": jti,
            },
            self._secret,
            algorithm=self._algorithm,
        )
        return token, jti, expires_at

    def decode(self, token: str, expected_type: TokenType) -> DecodedToken:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["sub", "type", "iat", "exp", "jti"]},
            )
            token_type = TokenType(payload["type"])
            subject = UUID(payload["sub"])
            jti = payload["jti"]
            issued_at = datetime.fromtimestamp(payload["iat"], UTC)
            expires_at = datetime.fromtimestamp(payload["exp"], UTC)
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise InvalidTokenError("Invalid authentication token") from exc

        if token_type is not expected_type or not isinstance(jti, str) or not jti:
            raise InvalidTokenError("Invalid authentication token")

        return DecodedToken(
            subject=subject,
            token_type=token_type,
            jti=jti,
            issued_at=issued_at,
            expires_at=expires_at,
        )
