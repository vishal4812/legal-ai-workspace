from fastapi import APIRouter, HTTPException, Request, Response, status

from app.config import Settings
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegistrationRequest,
    TokenResponse,
    UserResponse,
)
from app.security.dependencies import AuthServiceDependency, CurrentActiveUser, authentication_error
from app.security.exceptions import AuthenticationError, DuplicateEmailError, InactiveUserError
from app.security.tokens import TokenPair

router = APIRouter()


def set_refresh_cookie(response: Response, pair: TokenPair, settings: Settings) -> None:
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=pair.refresh_token,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )


def token_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse(access_token=pair.access_token, expires_in=pair.access_expires_in)


def resolve_refresh_token(
    request: Request,
    payload: RefreshTokenRequest | None,
) -> str:
    raw_token = payload.refresh_token if payload else None
    raw_token = raw_token or request.cookies.get(request.app.state.settings.auth_refresh_cookie_name)
    if not raw_token:
        raise authentication_error()
    return raw_token


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    description="Create a local user account. Email verification is intentionally deferred.",
)
async def register(request: RegistrationRequest, service: AuthServiceDependency) -> UserResponse:
    try:
        user = await service.register(request)
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered") from exc
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    description="Authenticate credentials, return an access token, and set a rotating HttpOnly refresh cookie.",
)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    service: AuthServiceDependency,
) -> TokenResponse:
    try:
        pair = await service.login(payload)
    except AuthenticationError as exc:
        raise authentication_error() from exc
    except InactiveUserError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user") from exc
    set_refresh_cookie(response, pair, request.app.state.settings)
    return token_response(pair)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    description="Rotate a valid refresh session. Browsers use the HttpOnly cookie; API clients may send a token body.",
)
async def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    payload: RefreshTokenRequest | None = None,
) -> TokenResponse:
    raw_token = resolve_refresh_token(request, payload)
    try:
        pair = await service.refresh(raw_token)
    except AuthenticationError as exc:
        raise authentication_error() from exc
    except InactiveUserError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user") from exc
    set_refresh_cookie(response, pair, request.app.state.settings)
    return token_response(pair)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Revoke the presented refresh session and remove its browser cookie.",
)
async def logout(
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    payload: RefreshTokenRequest | None = None,
) -> None:
    raw_token = resolve_refresh_token(request, payload)
    try:
        await service.logout(raw_token)
    except AuthenticationError as exc:
        raise authentication_error() from exc
    response.delete_cookie(
        key=request.app.state.settings.auth_refresh_cookie_name,
        path="/api/v1/auth",
        httponly=True,
        secure=request.app.state.settings.auth_cookie_secure,
        samesite="lax",
    )


@router.get(
    "/me",
    response_model=UserResponse,
    description="Return the active user identified by a valid access token.",
)
async def me(user: CurrentActiveUser) -> UserResponse:
    return UserResponse.model_validate(user)
