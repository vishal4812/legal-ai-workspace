from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.phase3_helpers import add_member, create_account, create_workspace


async def test_members_can_list_only_safe_member_fields(client: AsyncClient) -> None:
    owner, owner_headers = await create_account(client, "owner@example.com")
    member, member_headers = await create_account(client, "member@example.com")
    workspace = await create_workspace(client, owner_headers)
    await add_member(client, workspace["id"], owner_headers, member["email"], "MEMBER")

    response = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/members", headers=member_headers
    )

    assert response.status_code == 200
    assert {item["user_id"] for item in response.json()} == {owner["id"], member["id"]}
    serialized = response.text.casefold()
    assert "password" not in serialized
    assert "refresh" not in serialized
    assert "security" not in serialized


@pytest.mark.parametrize(
    ("actor_role", "expected"),
    [("ADMIN", 201), ("MEMBER", 403), ("VIEWER", 403)],
)
async def test_add_member_role_matrix(
    client: AsyncClient, actor_role: str, expected: int
) -> None:
    _, owner_headers = await create_account(client, f"owner-{actor_role}@example.com")
    actor, actor_headers = await create_account(
        client, f"actor-{actor_role}@example.com"
    )
    target, _ = await create_account(client, f"target-{actor_role}@example.com")
    workspace = await create_workspace(client, owner_headers)
    await add_member(
        client, workspace["id"], owner_headers, actor["email"], actor_role
    )

    response = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        headers=actor_headers,
        json={"email": target["email"], "role": "VIEWER"},
    )

    assert response.status_code == expected


async def test_duplicate_and_nonexistent_members_are_rejected(
    client: AsyncClient,
) -> None:
    _, headers = await create_account(client, "owner@example.com")
    member, _ = await create_account(client, "member@example.com")
    workspace = await create_workspace(client, headers)
    await add_member(client, workspace["id"], headers, member["email"], "MEMBER")

    duplicate = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        headers=headers,
        json={"email": member["email"].upper(), "role": "VIEWER"},
    )
    missing = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        headers=headers,
        json={"email": "missing@example.com", "role": "MEMBER"},
    )

    assert duplicate.status_code == 409
    assert missing.status_code == 404
    assert missing.json() == {"detail": "User account not found"}


async def test_owner_role_cannot_be_assigned_or_changed(
    client: AsyncClient,
) -> None:
    owner, headers = await create_account(client, "owner@example.com")
    member, _ = await create_account(client, "member@example.com")
    workspace = await create_workspace(client, headers)

    assign = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        headers=headers,
        json={"email": member["email"], "role": "OWNER"},
    )
    owner_change = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}/members/{owner['id']}",
        headers=headers,
        json={"role": "MEMBER"},
    )

    assert assign.status_code == 422
    assert owner_change.status_code == 409


async def test_only_owner_can_change_member_roles(client: AsyncClient) -> None:
    _, owner_headers = await create_account(client, "owner@example.com")
    admin, admin_headers = await create_account(client, "admin@example.com")
    member, _ = await create_account(client, "member@example.com")
    workspace = await create_workspace(client, owner_headers)
    await add_member(client, workspace["id"], owner_headers, admin["email"], "ADMIN")
    await add_member(client, workspace["id"], owner_headers, member["email"], "MEMBER")

    owner_change = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}/members/{member['id']}",
        headers=owner_headers,
        json={"role": "VIEWER"},
    )
    admin_change = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}/members/{member['id']}",
        headers=admin_headers,
        json={"role": "ADMIN"},
    )

    assert owner_change.status_code == 200
    assert owner_change.json()["role"] == "VIEWER"
    assert admin_change.status_code == 403


async def test_member_removal_permissions_and_owner_invariant(
    client: AsyncClient,
) -> None:
    owner, owner_headers = await create_account(client, "owner@example.com")
    admin, admin_headers = await create_account(client, "admin@example.com")
    admin2, _ = await create_account(client, "admin2@example.com")
    member, _ = await create_account(client, "member@example.com")
    viewer, _ = await create_account(client, "viewer@example.com")
    workspace = await create_workspace(client, owner_headers)
    for user, role in [
        (admin, "ADMIN"),
        (admin2, "ADMIN"),
        (member, "MEMBER"),
        (viewer, "VIEWER"),
    ]:
        await add_member(client, workspace["id"], owner_headers, user["email"], role)

    assert (
        await client.delete(
            f"/api/v1/workspaces/{workspace['id']}/members/{member['id']}",
            headers=admin_headers,
        )
    ).status_code == 204
    assert (
        await client.delete(
            f"/api/v1/workspaces/{workspace['id']}/members/{admin2['id']}",
            headers=admin_headers,
        )
    ).status_code == 403
    assert (
        await client.delete(
            f"/api/v1/workspaces/{workspace['id']}/members/{owner['id']}",
            headers=owner_headers,
        )
    ).status_code == 409
    assert (
        await client.delete(
            f"/api/v1/workspaces/{workspace['id']}/members/{viewer['id']}",
            headers=owner_headers,
        )
    ).status_code == 204


async def test_member_and_viewer_cannot_remove_members(client: AsyncClient) -> None:
    _, owner_headers = await create_account(client, "owner@example.com")
    member, member_headers = await create_account(client, "member@example.com")
    viewer, viewer_headers = await create_account(client, "viewer@example.com")
    target, _ = await create_account(client, "target@example.com")
    workspace = await create_workspace(client, owner_headers)
    for user, role in [(member, "MEMBER"), (viewer, "VIEWER"), (target, "VIEWER")]:
        await add_member(client, workspace["id"], owner_headers, user["email"], role)

    for headers in (member_headers, viewer_headers):
        response = await client.delete(
            f"/api/v1/workspaces/{workspace['id']}/members/{target['id']}",
            headers=headers,
        )
        assert response.status_code == 403
