from __future__ import annotations

from typing import Any

from httpx import AsyncClient


async def create_account(
    client: AsyncClient,
    email: str,
    *,
    first_name: str = "Legal",
    last_name: str = "User",
) -> tuple[dict[str, Any], dict[str, str]]:
    password = "correct-horse-battery"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    assert response.status_code == 201, response.text
    user = response.json()
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    return user, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def create_workspace(
    client: AsyncClient, headers: dict[str, str], name: str = "Legal Workspace"
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": name, "description": "Confidential matters"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def add_member(
    client: AsyncClient,
    workspace_id: str,
    owner_headers: dict[str, str],
    email: str,
    role: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        headers=owner_headers,
        json={"email": email, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()
