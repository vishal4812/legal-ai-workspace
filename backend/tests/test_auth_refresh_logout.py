from datetime import UTC, datetime, timedelta
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.security.tokens import TokenManager, TokenType
from tests.auth_helpers import DEFAULT_USER, register_and_login

DEFAULT_UUID = UUID("00000000-0000-0000-0000-000000000001")


async def test_valid_refresh_rotates_token(client: AsyncClient, session: AsyncSession) -> None:
    _, old_refresh = await register_and_login(client)

    response = await client.post("/api/v1/auth/refresh")
    new_refresh = client.cookies.get("legal_master_refresh")

    assert response.status_code == 200
    assert new_refresh is not None and new_refresh != old_refresh
    records = list((await session.scalars(select(RefreshToken))).all())
    assert len(records) == 2
    assert sum(record.revoked_at is not None for record in records) == 1


async def test_rotated_refresh_token_cannot_be_reused(client: AsyncClient) -> None:
    _, old_refresh = await register_and_login(client)
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )

    assert response.status_code == 401


async def test_expired_refresh_token_is_rejected(
    client: AsyncClient,
    test_settings: Settings,
) -> None:
    token, _, _ = TokenManager(test_settings).create_token(
        DEFAULT_UUID,
        TokenType.REFRESH,
        timedelta(seconds=-1),
    )

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})

    assert response.status_code == 401


async def test_invalid_refresh_token_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not-a-jwt"},
    )

    assert response.status_code == 401


async def test_access_token_cannot_be_used_as_refresh(client: AsyncClient) -> None:
    access_token, _ = await register_and_login(client)

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )

    assert response.status_code == 401


async def test_revoked_refresh_token_is_rejected(
    client: AsyncClient,
    session: AsyncSession,
    test_settings: Settings,
) -> None:
    _, refresh_token = await register_and_login(client)
    decoded = TokenManager(test_settings).decode(refresh_token, TokenType.REFRESH)
    record = await session.scalar(select(RefreshToken).where(RefreshToken.token_jti == decoded.jti))
    assert record is not None
    record.revoked_at = datetime.now(UTC)
    await session.commit()

    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 401


async def test_inactive_user_cannot_refresh(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await register_and_login(client)
    user = await session.scalar(select(User).where(User.email == DEFAULT_USER["email"]))
    assert user is not None
    user.is_active = False
    await session.commit()

    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 403


async def test_logout_revokes_refresh_and_clears_cookie(client: AsyncClient) -> None:
    _, refresh_token = await register_and_login(client)

    response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert client.cookies.get("legal_master_refresh") is None
    reuse = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert reuse.status_code == 401


async def test_logout_rejects_invalid_refresh(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "not-a-jwt"},
    )

    assert response.status_code == 401
