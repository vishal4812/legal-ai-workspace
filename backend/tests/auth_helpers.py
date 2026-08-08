from __future__ import annotations

from typing import Any

from httpx import AsyncClient, Response

DEFAULT_USER: dict[str, Any] = {
    "email": "lawyer@example.com",
    "password": "correct-horse-battery",
    "first_name": "Avery",
    "last_name": "Counsel",
}


async def register_user(client: AsyncClient, **overrides: Any) -> Response:
    payload = {**DEFAULT_USER, **overrides}
    return await client.post("/api/v1/auth/register", json=payload)


async def login_user(client: AsyncClient, **overrides: Any) -> Response:
    payload = {
        "email": overrides.get("email", DEFAULT_USER["email"]),
        "password": overrides.get("password", DEFAULT_USER["password"]),
    }
    return await client.post("/api/v1/auth/login", json=payload)


async def register_and_login(client: AsyncClient) -> tuple[str, str]:
    assert (await register_user(client)).status_code == 201
    response = await login_user(client)
    assert response.status_code == 200
    refresh_token = client.cookies.get("legal_master_refresh")
    assert refresh_token is not None
    return response.json()["access_token"], refresh_token
