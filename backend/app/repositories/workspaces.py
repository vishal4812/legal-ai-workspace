from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember


async def list_user_workspaces(
    session: AsyncSession, user_id: UUID
) -> list[tuple[Workspace, WorkspaceMember]]:
    result = await session.execute(
        select(Workspace, WorkspaceMember)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.created_at.desc())
    )
    return list(result.tuples().all())


async def get_membership(
    session: AsyncSession, workspace_id: UUID, user_id: UUID
) -> WorkspaceMember | None:
    return await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )


async def get_workspace_and_membership(
    session: AsyncSession, workspace_id: UUID, user_id: UUID
) -> tuple[Workspace, WorkspaceMember] | None:
    result = await session.execute(
        select(Workspace, WorkspaceMember)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(Workspace.id == workspace_id, WorkspaceMember.user_id == user_id)
    )
    return result.tuples().one_or_none()


async def list_workspace_members(
    session: AsyncSession, workspace_id: UUID
) -> list[tuple[WorkspaceMember, User]]:
    result = await session.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.created_at.asc())
    )
    return list(result.tuples().all())


async def get_workspace_member_with_user(
    session: AsyncSession, workspace_id: UUID, user_id: UUID
) -> tuple[WorkspaceMember, User] | None:
    result = await session.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    return result.tuples().one_or_none()
