from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.user import User


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def get_refresh_token_by_jti(
    session: AsyncSession,
    token_jti: str,
    *,
    for_update: bool = False,
) -> RefreshToken | None:
    statement = select(RefreshToken).where(RefreshToken.token_jti == token_jti)
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)
