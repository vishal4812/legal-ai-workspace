from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import DatabaseSession
from app.models.user import User
from app.repositories.auth import get_user_by_id
from app.security.tokens import InvalidTokenError, TokenManager, TokenType
from app.services.auth import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_auth_service(request: Request, session: DatabaseSession) -> AuthService:
    return AuthService(session, TokenManager(request.app.state.settings))


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    request: Request,
    session: DatabaseSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise authentication_error()
    try:
        decoded = TokenManager(request.app.state.settings).decode(
            credentials.credentials,
            TokenType.ACCESS,
        )
    except InvalidTokenError as exc:
        raise authentication_error() from exc

    user = await get_user_by_id(session, decoded.subject)
    if user is None:
        raise authentication_error()
    return user


async def get_current_active_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return user


CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
