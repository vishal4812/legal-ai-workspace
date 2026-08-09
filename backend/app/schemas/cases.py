from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.case import CaseStatus
from app.schemas.workspaces import normalize_optional_text, normalize_required_text


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    reference_number: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=10_000)
    status: CaseStatus = CaseStatus.ACTIVE

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("reference_number", "description")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class CaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    reference_number: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=10_000)
    status: CaseStatus | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return normalize_required_text(value) if value is not None else None

    @field_validator("reference_number", "description")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    reference_number: str | None
    description: str | None
    status: CaseStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    is_active: bool
