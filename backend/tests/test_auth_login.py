from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from tests.auth_helpers import DEFAULT_USER, login_user, register_user


async def test_correct_credentials_issue_access_and_http_only_refresh(client: AsyncClient) -> None:
    await register_user(client)

    response = await login_user(client)

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["expires_in"] == 1800
    assert "refresh_token" not in response.json()
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


async def test_wrong_password_uses_generic_error(client: AsyncClient) -> None:
    await register_user(client)

    response = await login_user(client, password="wrong-password")

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


async def test_unknown_email_uses_same_generic_error(client: AsyncClient) -> None:
    response = await login_user(client, email="unknown@example.com", password="wrong-password")

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


async def test_inactive_user_cannot_login(client: AsyncClient, session: AsyncSession) -> None:
    await register_user(client)
    user = await session.scalar(select(User).where(User.email == DEFAULT_USER["email"]))
    assert user is not None
    user.is_active = False
    await session.commit()

    response = await login_user(client)

    assert response.status_code == 403
    assert response.json() == {"detail": "Inactive user"}


async def test_login_email_is_normalized(client: AsyncClient) -> None:
    await register_user(client)

    response = await login_user(client, email="  LAWYER@EXAMPLE.COM ")

    assert response.status_code == 200


async def test_login_updates_last_login(client: AsyncClient, session: AsyncSession) -> None:
    await register_user(client)
    user = await session.scalar(select(User).where(User.email == DEFAULT_USER["email"]))
    assert user is not None and user.last_login_at is None

    await login_user(client)
    await session.refresh(user)

    assert user.last_login_at is not None
