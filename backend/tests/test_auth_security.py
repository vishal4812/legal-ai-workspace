from uuid import uuid4

import jwt
import pytest
from httpx import AsyncClient

from app.config import Settings
from app.security.tokens import TokenManager, TokenType
from tests.auth_helpers import register_and_login


async def test_token_response_contains_no_refresh_or_security_fields(client: AsyncClient) -> None:
    await register_and_login(client)
    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert set(response.json()) == {"access_token", "token_type", "expires_in"}


async def test_jwt_uses_secret_from_settings(test_settings: Settings) -> None:
    pair = TokenManager(test_settings).create_pair(uuid4())

    claims = jwt.decode(
        pair.access_token,
        test_settings.jwt_secret.get_secret_value(),
        algorithms=[test_settings.jwt_algorithm],
    )
    assert set(("sub", "type", "iat", "exp", "jti")).issubset(claims)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(pair.access_token, "a-different-secret-that-is-long-enough", algorithms=["HS256"])


async def test_access_and_refresh_tokens_have_distinct_types(test_settings: Settings) -> None:
    pair = TokenManager(test_settings).create_pair(uuid4())

    access = TokenManager(test_settings).decode(pair.access_token, TokenType.ACCESS)
    refresh = TokenManager(test_settings).decode(pair.refresh_token, TokenType.REFRESH)

    assert access.token_type is TokenType.ACCESS
    assert refresh.token_type is TokenType.REFRESH
    assert access.jti != refresh.jti
