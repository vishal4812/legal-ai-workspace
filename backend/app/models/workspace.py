from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import utc_now

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.user import User
    from app.models.workspace_member import WorkspaceMember


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship(back_populates="owned_workspaces", foreign_keys=[owner_id])
    memberships: Mapped[list["WorkspaceMember"]] = relationship(back_populates="workspace")
    cases: Mapped[list["Case"]] = relationship(back_populates="workspace")
