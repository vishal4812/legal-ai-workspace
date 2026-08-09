from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.workspace_member import WorkspaceRole
from app.schemas.auth import normalize_email


def normalize_required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Value cannot be blank")
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class WorkspaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return normalize_required_text(value) if value is not None else None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    owner_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    current_user_role: WorkspaceRole


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: WorkspaceRole

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email_field(cls, value: EmailStr) -> str:
        return normalize_email(str(value))

    @field_validator("role")
    @classmethod
    def disallow_owner(cls, value: WorkspaceRole) -> WorkspaceRole:
        if value is WorkspaceRole.OWNER:
            raise ValueError("OWNER cannot be assigned through the membership API")
        return value


class MemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: WorkspaceRole

    @field_validator("role")
    @classmethod
    def disallow_owner(cls, value: WorkspaceRole) -> WorkspaceRole:
        if value is WorkspaceRole.OWNER:
            raise ValueError("Ownership transfer is not supported")
        return value


class WorkspaceMemberResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    email: EmailStr
    first_name: str | None
    last_name: str | None
    role: WorkspaceRole
    created_at: datetime
    updated_at: datetime
