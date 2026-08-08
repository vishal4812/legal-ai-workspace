from datetime import timedelta
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.user import User
from app.security.tokens import TokenManager, TokenType
from tests.auth_helpers import DEFAULT_USER, register_and_login


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_valid_access_token_returns_current_user(client: AsyncClient) -> None:
    access_token, _ = await register_and_login(client)

    response = await client.get("/api/v1/auth/me", headers=bearer(access_token))

    assert response.status_code == 200
    assert response.json()["email"] == DEFAULT_USER["email"]
    assert "password_hash" not in response.json()


async def test_missing_access_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_invalid_access_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me", headers=bearer("not-a-jwt"))

    assert response.status_code == 401


async def test_expired_access_token_is_rejected(
    client: AsyncClient,
    test_settings: Settings,
) -> None:
    token, _, _ = TokenManager(test_settings).create_token(
        uuid4(),
        TokenType.ACCESS,
        timedelta(seconds=-1),
    )

    response = await client.get("/api/v1/auth/me", headers=bearer(token))

    assert response.status_code == 401


async def test_refresh_token_cannot_be_used_as_access(client: AsyncClient) -> None:
    _, refresh_token = await register_and_login(client)

    response = await client.get("/api/v1/auth/me", headers=bearer(refresh_token))

    assert response.status_code == 401


async def test_access_token_for_unknown_user_is_rejected(
    client: AsyncClient,
    test_settings: Settings,
) -> None:
    token, _, _ = TokenManager(test_settings).create_token(
        uuid4(),
        TokenType.ACCESS,
        timedelta(minutes=5),
    )

    response = await client.get("/api/v1/auth/me", headers=bearer(token))

    assert response.status_code == 401


async def test_inactive_user_access_is_forbidden(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    access_token, _ = await register_and_login(client)
    user = await session.scalar(select(User).where(User.email == DEFAULT_USER["email"]))
    assert user is not None
    user.is_active = False
    await session.commit()

    response = await client.get("/api/v1/auth/me", headers=bearer(access_token))

    assert response.status_code == 403
