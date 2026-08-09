from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseStatus
from app.repositories.cases import list_workspace_cases
from app.schemas.cases import CaseCreate, CaseUpdate
from app.security.authorization import CaseAccess, WorkspaceAccess


class CaseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, access: WorkspaceAccess, payload: CaseCreate) -> Case:
        case = Case(
            workspace_id=access.workspace.id,
            name=payload.name,
            reference_number=payload.reference_number,
            description=payload.description,
            status=payload.status,
            created_by=access.user.id,
        )
        self._session.add(case)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(case)
        return case

    async def list_for_workspace(self, workspace_id: UUID) -> list[Case]:
        return await list_workspace_cases(self._session, workspace_id)

    async def update(self, access: CaseAccess, payload: CaseUpdate) -> Case:
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(access.case, field, value)
        await self._session.commit()
        await self._session.refresh(access.case)
        return access.case

    async def archive(self, access: CaseAccess) -> Case:
        access.case.is_active = False
        access.case.status = CaseStatus.ARCHIVED
        await self._session.commit()
        await self._session.refresh(access.case)
        return access.case
