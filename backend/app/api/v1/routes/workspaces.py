from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.database import DatabaseSession
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.workspaces import (
    MemberCreate,
    MemberRoleUpdate,
    WorkspaceCreate,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.security.authorization import (
    WorkspaceAccess,
    WorkspaceAccessDependency,
    require_workspace_roles,
)
from app.security.dependencies import CurrentActiveUser
from app.services.workspaces import WorkspaceService

router = APIRouter()


def workspace_response(
    workspace: Workspace, membership: WorkspaceMember
) -> WorkspaceResponse:
    return WorkspaceResponse(
        **{
            column: getattr(workspace, column)
            for column in (
                "id",
                "name",
                "description",
                "owner_id",
                "is_active",
                "created_at",
                "updated_at",
            )
        },
        current_user_role=membership.role,
    )


def member_response(
    membership: WorkspaceMember, user: User
) -> WorkspaceMemberResponse:
    return WorkspaceMemberResponse(
        id=membership.id,
        workspace_id=membership.workspace_id,
        user_id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role=membership.role,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    session: DatabaseSession,
    user: CurrentActiveUser,
) -> WorkspaceResponse:
    workspace, membership = await WorkspaceService(session).create(payload, user)
    return workspace_response(workspace, membership)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    session: DatabaseSession,
    user: CurrentActiveUser,
) -> list[WorkspaceResponse]:
    records = await WorkspaceService(session).list_for_user(user.id)
    return [workspace_response(workspace, membership) for workspace, membership in records]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(access: WorkspaceAccessDependency) -> WorkspaceResponse:
    return workspace_response(access.workspace, access.membership)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    payload: WorkspaceUpdate,
    session: DatabaseSession,
    access: Annotated[
        WorkspaceAccess,
        Depends(require_workspace_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)),
    ],
) -> WorkspaceResponse:
    workspace = await WorkspaceService(session).update(access, payload)
    return workspace_response(workspace, access.membership)


@router.delete("/{workspace_id}", response_model=WorkspaceResponse)
async def archive_workspace(
    session: DatabaseSession,
    access: Annotated[
        WorkspaceAccess,
        Depends(require_workspace_roles(WorkspaceRole.OWNER)),
    ],
) -> WorkspaceResponse:
    workspace = await WorkspaceService(session).archive(access)
    return workspace_response(workspace, access.membership)


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberResponse])
async def list_members(
    session: DatabaseSession,
    access: WorkspaceAccessDependency,
) -> list[WorkspaceMemberResponse]:
    records = await WorkspaceService(session).list_members(access.workspace.id)
    return [member_response(membership, user) for membership, user in records]


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    payload: MemberCreate,
    session: DatabaseSession,
    access: Annotated[
        WorkspaceAccess,
        Depends(require_workspace_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)),
    ],
) -> WorkspaceMemberResponse:
    membership, user = await WorkspaceService(session).add_member(
        access.workspace.id, payload
    )
    return member_response(membership, user)


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMemberResponse,
)
async def change_member_role(
    user_id: UUID,
    payload: MemberRoleUpdate,
    session: DatabaseSession,
    access: Annotated[
        WorkspaceAccess,
        Depends(require_workspace_roles(WorkspaceRole.OWNER)),
    ],
) -> WorkspaceMemberResponse:
    membership, user = await WorkspaceService(session).change_member_role(
        access.workspace.id, user_id, payload
    )
    return member_response(membership, user)


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    user_id: UUID,
    session: DatabaseSession,
    access: Annotated[
        WorkspaceAccess,
        Depends(require_workspace_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)),
    ],
) -> Response:
    await WorkspaceService(session).remove_member(access, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
