from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case


async def list_workspace_cases(session: AsyncSession, workspace_id: UUID) -> list[Case]:
    result = await session.scalars(
        select(Case).where(Case.workspace_id == workspace_id).order_by(Case.created_at.desc())
    )
    return list(result.all())


async def get_workspace_case(
    session: AsyncSession, workspace_id: UUID, case_id: UUID
) -> Case | None:
    return await session.scalar(
        select(Case).where(Case.id == case_id, Case.workspace_id == workspace_id)
    )
