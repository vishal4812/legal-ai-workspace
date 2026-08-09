from __future__ import annotations

from uuid import UUID

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.repositories.auth import get_user_by_email
from app.repositories.workspaces import (
    get_membership,
    get_workspace_member_with_user,
    list_user_workspaces,
    list_workspace_members,
)
from app.schemas.workspaces import MemberCreate, MemberRoleUpdate, WorkspaceCreate, WorkspaceUpdate
from app.security.authorization import WorkspaceAccess
from app.services.errors import DomainError


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, payload: WorkspaceCreate, owner: User
    ) -> tuple[Workspace, WorkspaceMember]:
        workspace = Workspace(
            name=payload.name,
            description=payload.description,
            owner_id=owner.id,
        )
        membership = WorkspaceMember(
            workspace=workspace,
            user_id=owner.id,
            role=WorkspaceRole.OWNER,
        )
        self._session.add_all([workspace, membership])
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(workspace)
        await self._session.refresh(membership)
        return workspace, membership

    async def list_for_user(self, user_id: UUID) -> list[tuple[Workspace, WorkspaceMember]]:
        return await list_user_workspaces(self._session, user_id)

    async def update(self, access: WorkspaceAccess, payload: WorkspaceUpdate) -> Workspace:
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(access.workspace, field, value)
        await self._session.commit()
        await self._session.refresh(access.workspace)
        return access.workspace

    async def archive(self, access: WorkspaceAccess) -> Workspace:
        access.workspace.is_active = False
        await self._session.commit()
        await self._session.refresh(access.workspace)
        return access.workspace

    async def list_members(
        self, workspace_id: UUID
    ) -> list[tuple[WorkspaceMember, User]]:
        return await list_workspace_members(self._session, workspace_id)

    async def add_member(
        self, workspace_id: UUID, payload: MemberCreate
    ) -> tuple[WorkspaceMember, User]:
        user = await get_user_by_email(self._session, str(payload.email))
        if user is None:
            raise DomainError(status.HTTP_404_NOT_FOUND, "User account not found")
        if await get_membership(self._session, workspace_id, user.id):
            raise DomainError(status.HTTP_409_CONFLICT, "User is already a workspace member")

        membership = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=user.id,
            role=payload.role,
        )
        self._session.add(membership)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DomainError(
                status.HTTP_409_CONFLICT, "User is already a workspace member"
            ) from exc
        await self._session.refresh(membership)
        return membership, user

    async def change_member_role(
        self, workspace_id: UUID, user_id: UUID, payload: MemberRoleUpdate
    ) -> tuple[WorkspaceMember, User]:
        record = await get_workspace_member_with_user(self._session, workspace_id, user_id)
        if record is None:
            raise DomainError(status.HTTP_404_NOT_FOUND, "Workspace member not found")
        membership, user = record
        if membership.role is WorkspaceRole.OWNER:
            raise DomainError(
                status.HTTP_409_CONFLICT,
                "Workspace owner role cannot be changed; ownership transfer is not supported",
            )
        membership.role = payload.role
        await self._session.commit()
        await self._session.refresh(membership)
        return membership, user

    async def remove_member(
        self, access: WorkspaceAccess, user_id: UUID
    ) -> None:
        record = await get_workspace_member_with_user(
            self._session, access.workspace.id, user_id
        )
        if record is None:
            raise DomainError(status.HTTP_404_NOT_FOUND, "Workspace member not found")
        membership, _ = record
        if membership.role is WorkspaceRole.OWNER or user_id == access.workspace.owner_id:
            raise DomainError(status.HTTP_409_CONFLICT, "Workspace owner cannot be removed")
        if (
            access.membership.role is WorkspaceRole.ADMIN
            and membership.role not in {WorkspaceRole.MEMBER, WorkspaceRole.VIEWER}
        ):
            raise DomainError(
                status.HTTP_403_FORBIDDEN,
                "Administrators can only remove members and viewers",
            )
        await self._session.delete(membership)
        await self._session.commit()
