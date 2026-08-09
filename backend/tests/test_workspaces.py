from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from tests.phase3_helpers import add_member, create_account, create_workspace


async def test_create_workspace_atomically_creates_owner_membership(
    client: AsyncClient, session: AsyncSession
) -> None:
    owner, headers = await create_account(client, "owner@example.com")

    response = await client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "  My Legal Workspace  ", "description": "  Legal work  "},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "My Legal Workspace"
    assert body["owner_id"] == owner["id"]
    assert body["current_user_role"] == "OWNER"
    workspace = await session.get(Workspace, UUID(body["id"]))
    membership = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == UUID(owner["id"]),
        )
    )
    assert workspace is not None
    assert membership is not None
    assert membership.role is WorkspaceRole.OWNER


async def test_list_and_get_workspaces_are_isolated_by_membership(
    client: AsyncClient,
) -> None:
    _, headers_a = await create_account(client, "a@example.com")
    _, headers_b = await create_account(client, "b@example.com")
    workspace_a = await create_workspace(client, headers_a, "Workspace A")
    workspace_b = await create_workspace(client, headers_b, "Workspace B")

    list_a = await client.get("/api/v1/workspaces", headers=headers_a)
    list_b = await client.get("/api/v1/workspaces", headers=headers_b)

    assert [item["id"] for item in list_a.json()] == [workspace_a["id"]]
    assert [item["id"] for item in list_b.json()] == [workspace_b["id"]]
    assert (
        await client.get(
            f"/api/v1/workspaces/{workspace_b['id']}", headers=headers_a
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/workspaces/{workspace_a['id']}", headers=headers_b
        )
    ).status_code == 404


@pytest.mark.parametrize(
    ("role", "expected"),
    [("ADMIN", 200), ("MEMBER", 403), ("VIEWER", 403)],
)
async def test_workspace_update_role_matrix(
    client: AsyncClient, role: str, expected: int
) -> None:
    _, owner_headers = await create_account(client, f"owner-{role}@example.com")
    member, member_headers = await create_account(client, f"{role.lower()}@example.com")
    workspace = await create_workspace(client, owner_headers)
    await add_member(client, workspace["id"], owner_headers, member["email"], role)

    response = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}",
        headers=member_headers,
        json={"name": f"{role} Updated"},
    )

    assert response.status_code == expected
    if expected == 200:
        assert response.json()["name"] == f"{role} Updated"


async def test_owner_can_update_and_soft_delete_workspace(
    client: AsyncClient,
) -> None:
    _, headers = await create_account(client, "workspace-owner@example.com")
    workspace = await create_workspace(client, headers)

    update = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}",
        headers=headers,
        json={"description": "Updated", "is_active": True},
    )
    archived = await client.delete(
        f"/api/v1/workspaces/{workspace['id']}", headers=headers
    )

    assert update.status_code == 200
    assert update.json()["description"] == "Updated"
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False
    retained = await client.get(
        f"/api/v1/workspaces/{workspace['id']}", headers=headers
    )
    assert retained.status_code == 200
    assert retained.json()["is_active"] is False


@pytest.mark.parametrize("role", ["ADMIN", "MEMBER", "VIEWER"])
async def test_only_owner_can_delete_workspace(
    client: AsyncClient, role: str
) -> None:
    _, owner_headers = await create_account(client, f"delete-owner-{role}@example.com")
    member, member_headers = await create_account(
        client, f"delete-{role.lower()}@example.com"
    )
    workspace = await create_workspace(client, owner_headers)
    await add_member(client, workspace["id"], owner_headers, member["email"], role)

    response = await client.delete(
        f"/api/v1/workspaces/{workspace['id']}", headers=member_headers
    )

    assert response.status_code == 403


async def test_workspace_input_validation(client: AsyncClient) -> None:
    _, headers = await create_account(client, "validation@example.com")
    assert (
        await client.post(
            "/api/v1/workspaces", headers=headers, json={"name": "   "}
        )
    ).status_code == 422
    workspace = await create_workspace(client, headers)
    assert (
        await client.patch(
            f"/api/v1/workspaces/{workspace['id']}",
            headers=headers,
            json={"owner_id": "84b21dce-5312-43d2-8b38-ea6891e32fcf"},
        )
    ).status_code == 422
