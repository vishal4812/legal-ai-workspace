from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.database import DatabaseSession
from app.models.workspace_member import WorkspaceRole
from app.schemas.cases import CaseCreate, CaseResponse, CaseUpdate
from app.security.authorization import (
    CaseAccess,
    CaseAccessDependency,
    WorkspaceAccess,
    WorkspaceAccessDependency,
    require_case_roles,
    require_workspace_roles,
)
from app.services.cases import CaseService

router = APIRouter()


@router.post(
    "/workspaces/{workspace_id}/cases",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_case(
    payload: CaseCreate,
    session: DatabaseSession,
    access: Annotated[
        WorkspaceAccess,
        Depends(
            require_workspace_roles(
                WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER
            )
        ),
    ],
) -> CaseResponse:
    case = await CaseService(session).create(access, payload)
    return CaseResponse.model_validate(case)


@router.get(
    "/workspaces/{workspace_id}/cases",
    response_model=list[CaseResponse],
)
async def list_cases(
    session: DatabaseSession,
    access: WorkspaceAccessDependency,
) -> list[CaseResponse]:
    cases = await CaseService(session).list_for_workspace(access.workspace.id)
    return [CaseResponse.model_validate(case) for case in cases]


@router.get(
    "/workspaces/{workspace_id}/cases/{case_id}",
    response_model=CaseResponse,
)
async def get_case(access: CaseAccessDependency) -> CaseResponse:
    return CaseResponse.model_validate(access.case)


@router.patch(
    "/workspaces/{workspace_id}/cases/{case_id}",
    response_model=CaseResponse,
)
async def update_case(
    payload: CaseUpdate,
    session: DatabaseSession,
    access: Annotated[
        CaseAccess,
        Depends(
            require_case_roles(
                WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER
            )
        ),
    ],
) -> CaseResponse:
    case = await CaseService(session).update(access, payload)
    return CaseResponse.model_validate(case)


@router.delete(
    "/workspaces/{workspace_id}/cases/{case_id}",
    response_model=CaseResponse,
)
async def archive_case(
    session: DatabaseSession,
    access: Annotated[
        CaseAccess,
        Depends(require_case_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)),
    ],
) -> CaseResponse:
    case = await CaseService(session).archive(access)
    return CaseResponse.model_validate(case)
