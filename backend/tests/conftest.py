from __future__ import annotations

import os

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://legal_master:password@localhost/legal_master_test")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-characters")

from app.config import Settings
from app.database import Base, get_session
from app.main import create_app
import app.models  # noqa: F401


@pytest_asyncio.fixture
async def test_settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite://",
        jwt_secret="test-secret-that-is-at-least-32-characters",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_days=7,
        environment="test",
    )


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as test_session:
        yield test_session

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def application(test_settings: Settings, session: AsyncSession) -> FastAPI:
    application = create_app(test_settings)

    async def override_session():
        yield session

    application.dependency_overrides[get_session] = override_session
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(application: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
