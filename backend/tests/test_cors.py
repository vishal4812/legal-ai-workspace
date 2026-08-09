import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)
async def test_local_loopback_origins_pass_cors_preflight(
    client: AsyncClient, origin: str
) -> None:
    response = await client.options(
        "/api/v1/auth/register",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_unconfigured_origin_fails_cors_preflight(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/auth/register",
        headers={
            "Origin": "http://attacker.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
