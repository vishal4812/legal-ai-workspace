from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.database import DatabaseSession
from app.models.case import Case
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.repositories.cases import get_workspace_case
from app.repositories.workspaces import get_workspace_and_membership
from app.security.dependencies import CurrentActiveUser


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace: Workspace
    membership: WorkspaceMember
    user: User


@dataclass(frozen=True)
class CaseAccess:
    workspace_access: WorkspaceAccess
    case: Case


async def get_workspace_access(
    workspace_id: UUID,
    session: DatabaseSession,
    user: CurrentActiveUser,
) -> WorkspaceAccess:
    record = await get_workspace_and_membership(session, workspace_id, user.id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    workspace, membership = record
    return WorkspaceAccess(workspace=workspace, membership=membership, user=user)


WorkspaceAccessDependency = Annotated[WorkspaceAccess, Depends(get_workspace_access)]


def require_workspace_roles(*allowed_roles: WorkspaceRole):
    allowed = frozenset(allowed_roles)

    async def dependency(access: WorkspaceAccessDependency) -> WorkspaceAccess:
        if access.membership.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient workspace permissions",
            )
        return access

    return dependency


async def get_case_access(
    case_id: UUID,
    session: DatabaseSession,
    access: WorkspaceAccessDependency,
) -> CaseAccess:
    case = await get_workspace_case(session, access.workspace.id, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return CaseAccess(workspace_access=access, case=case)


CaseAccessDependency = Annotated[CaseAccess, Depends(get_case_access)]


def require_case_roles(*allowed_roles: WorkspaceRole):
    allowed = frozenset(allowed_roles)

    async def dependency(access: CaseAccessDependency) -> CaseAccess:
        if access.workspace_access.membership.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient workspace permissions",
            )
        return access

    return dependency
