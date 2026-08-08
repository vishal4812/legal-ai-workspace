from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.security.passwords import verify_password
from tests.auth_helpers import DEFAULT_USER, register_user


async def test_successful_registration(client: AsyncClient) -> None:
    response = await register_user(client)

    assert response.status_code == 201
    assert response.json()["email"] == DEFAULT_USER["email"]
    assert response.json()["is_active"] is True
    assert response.json()["is_verified"] is False


async def test_duplicate_email_is_rejected_after_normalization(client: AsyncClient) -> None:
    assert (await register_user(client)).status_code == 201

    response = await register_user(client, email="  LAWYER@EXAMPLE.COM ")

    assert response.status_code == 409
    assert response.json() == {"detail": "Email is already registered"}


async def test_invalid_email_is_rejected(client: AsyncClient) -> None:
    response = await register_user(client, email="not-an-email")

    assert response.status_code == 422


async def test_short_password_is_rejected(client: AsyncClient) -> None:
    response = await register_user(client, password="short")

    assert response.status_code == 422


async def test_blank_password_is_rejected(client: AsyncClient) -> None:
    response = await register_user(client, password="        ")

    assert response.status_code == 422


async def test_email_and_names_are_normalized(client: AsyncClient) -> None:
    response = await register_user(
        client,
        email="  LAWYER@EXAMPLE.COM ",
        first_name="  Avery ",
        last_name="  ",
    )

    assert response.status_code == 201
    assert response.json()["email"] == "lawyer@example.com"
    assert response.json()["first_name"] == "Avery"
    assert response.json()["last_name"] is None


async def test_password_is_argon2id_hashed(client: AsyncClient, session: AsyncSession) -> None:
    await register_user(client)
    user = await session.scalar(select(User).where(User.email == DEFAULT_USER["email"]))

    assert user is not None
    assert user.password_hash != DEFAULT_USER["password"]
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(DEFAULT_USER["password"], user.password_hash)


async def test_registration_never_exposes_password_material(client: AsyncClient) -> None:
    response = await register_user(client)
    serialized = response.text.casefold()

    assert "password" not in serialized
    assert "argon2" not in serialized
