from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "legal-master-api"}


async def test_api_version_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1")

    assert response.status_code == 200
    assert response.json() == {"name": "LEGAL MASTER API", "version": "v1"}
