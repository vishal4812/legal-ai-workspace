from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.phase3_helpers import add_member, create_account, create_workspace


async def create_case(
    client: AsyncClient,
    workspace_id: str,
    headers: dict[str, str],
    name: str = "Smith v Jones",
) -> dict:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/cases",
        headers=headers,
        json={
            "name": name,
            "reference_number": "LM-2026-001",
            "description": "Contract dispute",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_case_crud_and_soft_archive(client: AsyncClient) -> None:
    owner, headers = await create_account(client, "owner@example.com")
    workspace = await create_workspace(client, headers)
    case = await create_case(client, workspace["id"], headers)

    assert case["workspace_id"] == workspace["id"]
    assert case["created_by"] == owner["id"]
    assert case["status"] == "ACTIVE"
    listed = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/cases", headers=headers
    )
    fetched = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/cases/{case['id']}", headers=headers
    )
    updated = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}/cases/{case['id']}",
        headers=headers,
        json={"name": "Updated matter", "status": "CLOSED"},
    )
    archived = await client.delete(
        f"/api/v1/workspaces/{workspace['id']}/cases/{case['id']}",
        headers=headers,
    )

    assert [item["id"] for item in listed.json()] == [case["id"]]
    assert fetched.status_code == 200
    assert updated.json()["status"] == "CLOSED"
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    assert archived.json()["is_active"] is False
    retained = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/cases/{case['id']}", headers=headers
    )
    assert retained.status_code == 200
    assert retained.json()["is_active"] is False


@pytest.mark.parametrize(
    ("role", "create_status", "update_status", "delete_status"),
    [
        ("ADMIN", 201, 200, 200),
        ("MEMBER", 201, 200, 403),
        ("VIEWER", 403, 403, 403),
    ],
)
async def test_case_role_matrix(
    client: AsyncClient,
    role: str,
    create_status: int,
    update_status: int,
    delete_status: int,
) -> None:
    _, owner_headers = await create_account(client, f"owner-{role}@example.com")
    actor, actor_headers = await create_account(client, f"{role.lower()}@example.com")
    workspace = await create_workspace(client, owner_headers)
    await add_member(client, workspace["id"], owner_headers, actor["email"], role)
    owner_case = await create_case(client, workspace["id"], owner_headers)

    created = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/cases",
        headers=actor_headers,
        json={"name": "Actor case"},
    )
    updated = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}/cases/{owner_case['id']}",
        headers=actor_headers,
        json={"description": "Role update"},
    )
    archived = await client.delete(
        f"/api/v1/workspaces/{workspace['id']}/cases/{owner_case['id']}",
        headers=actor_headers,
    )

    assert created.status_code == create_status
    assert updated.status_code == update_status
    assert archived.status_code == delete_status


async def test_workspace_case_mismatch_and_nonmember_are_not_found(
    client: AsyncClient,
) -> None:
    _, headers_a = await create_account(client, "a@example.com")
    _, headers_b = await create_account(client, "b@example.com")
    workspace_a = await create_workspace(client, headers_a, "Workspace A")
    workspace_b = await create_workspace(client, headers_b, "Workspace B")
    case_b = await create_case(client, workspace_b["id"], headers_b)

    mismatch = await client.get(
        f"/api/v1/workspaces/{workspace_a['id']}/cases/{case_b['id']}",
        headers=headers_a,
    )
    direct = await client.get(
        f"/api/v1/workspaces/{workspace_b['id']}/cases/{case_b['id']}",
        headers=headers_a,
    )

    assert mismatch.status_code == 404
    assert direct.status_code == 404


async def test_cross_tenant_workspace_membership_and_case_mutations_are_rejected(
    client: AsyncClient,
) -> None:
    user_a, headers_a = await create_account(client, "a@example.com")
    user_b, headers_b = await create_account(client, "b@example.com")
    workspace_a = await create_workspace(client, headers_a, "Workspace A")
    workspace_b = await create_workspace(client, headers_b, "Workspace B")
    case_b = await create_case(client, workspace_b["id"], headers_b)

    requests = [
        client.get(f"/api/v1/workspaces/{workspace_b['id']}", headers=headers_a),
        client.patch(
            f"/api/v1/workspaces/{workspace_b['id']}",
            headers=headers_a,
            json={"name": "Attack"},
        ),
        client.delete(f"/api/v1/workspaces/{workspace_b['id']}", headers=headers_a),
        client.get(
            f"/api/v1/workspaces/{workspace_b['id']}/members", headers=headers_a
        ),
        client.post(
            f"/api/v1/workspaces/{workspace_b['id']}/members",
            headers=headers_a,
            json={"email": user_a["email"], "role": "ADMIN"},
        ),
        client.patch(
            f"/api/v1/workspaces/{workspace_b['id']}/members/{user_b['id']}",
            headers=headers_a,
            json={"role": "MEMBER"},
        ),
        client.delete(
            f"/api/v1/workspaces/{workspace_b['id']}/members/{user_b['id']}",
            headers=headers_a,
        ),
        client.get(
            f"/api/v1/workspaces/{workspace_b['id']}/cases", headers=headers_a
        ),
        client.post(
            f"/api/v1/workspaces/{workspace_b['id']}/cases",
            headers=headers_a,
            json={"name": "Attack"},
        ),
        client.get(
            f"/api/v1/workspaces/{workspace_b['id']}/cases/{case_b['id']}",
            headers=headers_a,
        ),
        client.patch(
            f"/api/v1/workspaces/{workspace_b['id']}/cases/{case_b['id']}",
            headers=headers_a,
            json={"name": "Attack"},
        ),
        client.delete(
            f"/api/v1/workspaces/{workspace_b['id']}/cases/{case_b['id']}",
            headers=headers_a,
        ),
    ]
    results = await __import__("asyncio").gather(*requests)

    assert all(response.status_code == 404 for response in results)
    assert workspace_a["id"] != workspace_b["id"]


async def test_case_immutable_fields_are_rejected(client: AsyncClient) -> None:
    _, headers = await create_account(client, "owner@example.com")
    workspace = await create_workspace(client, headers)
    case = await create_case(client, workspace["id"], headers)

    response = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}/cases/{case['id']}",
        headers=headers,
        json={"workspace_id": workspace["id"], "created_by": case["created_by"]},
    )

    assert response.status_code == 422
