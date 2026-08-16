from __future__ import annotations

import argparse
import asyncio
import hashlib
from uuid import UUID, uuid4

import httpx
import pymupdf
from sqlalchemy import delete, select

from app.config import get_settings
from app.database import Database
from app.models.case import Case
from app.models.document import Document
from app.models.document_extraction import DocumentExtraction
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.storage.local import LocalStorageProvider


def make_pdf() -> bytes:
    document = pymupdf.open()
    first = document.new_page()
    first.insert_text((72, 72), "Phase 5 HTTP agreement text.")
    second = document.new_page()
    second.insert_text((72, 72), "Clause 2: 1,234.50; payable.")
    content = document.tobytes()
    document.close()
    return content


def require(response: httpx.Response, expected: int) -> dict[str, object]:
    if response.status_code != expected:
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path} returned "
            f"{response.status_code}: {response.text[:300]}"
        )
    return response.json() if response.content else {}


async def cleanup(
    user_ids: list[UUID],
    workspace_ids: list[UUID],
    case_ids: list[UUID],
    document_ids: list[UUID],
) -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    storage = LocalStorageProvider(settings.document_storage_path)
    try:
        async with database.session_factory() as session:
            if document_ids:
                keys = list(
                    (
                        await session.scalars(
                            select(Document.storage_key).where(Document.id.in_(document_ids))
                        )
                    ).all()
                )
                await session.execute(
                    delete(DocumentExtraction).where(
                        DocumentExtraction.document_id.in_(document_ids)
                    )
                )
                await session.execute(delete(Document).where(Document.id.in_(document_ids)))
                for key in keys:
                    storage.delete(key)
            if case_ids:
                await session.execute(delete(Case).where(Case.id.in_(case_ids)))
            if workspace_ids:
                await session.execute(
                    delete(WorkspaceMember).where(
                        WorkspaceMember.workspace_id.in_(workspace_ids)
                    )
                )
                await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
            if user_ids:
                await session.execute(
                    delete(RefreshToken).where(RefreshToken.user_id.in_(user_ids))
                )
                await session.execute(delete(User).where(User.id.in_(user_ids)))
            await session.commit()
    finally:
        await database.dispose()


async def run(base_url: str) -> None:
    suffix = uuid4().hex
    user_ids: list[UUID] = []
    workspace_ids: list[UUID] = []
    case_ids: list[UUID] = []
    document_ids: list[UUID] = []
    original = make_pdf()
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=120) as client:
            auth_headers: list[dict[str, str]] = []
            for actor in ("a", "b"):
                email = f"phase5-http-{actor}-{suffix}@example.com"
                registered = require(
                    await client.post(
                        "/api/v1/auth/register",
                        json={
                            "email": email,
                            "password": "correct-horse-battery",
                            "first_name": "HTTP",
                            "last_name": actor.upper(),
                        },
                    ),
                    201,
                )
                user_ids.append(UUID(str(registered["id"])))
                login = require(
                    await client.post(
                        "/api/v1/auth/login",
                        json={"email": email, "password": "correct-horse-battery"},
                    ),
                    200,
                )
                auth_headers.append(
                    {"Authorization": f"Bearer {login['access_token']}"}
                )

            workspace = require(
                await client.post(
                    "/api/v1/workspaces",
                    headers=auth_headers[0],
                    json={"name": f"Phase 5 HTTP {suffix}"},
                ),
                201,
            )
            workspace_ids.append(UUID(str(workspace["id"])))
            legal_case = require(
                await client.post(
                    f"/api/v1/workspaces/{workspace['id']}/cases",
                    headers=auth_headers[0],
                    json={"name": "HTTP extraction case"},
                ),
                201,
            )
            case_ids.append(UUID(str(legal_case["id"])))
            base = (
                f"/api/v1/workspaces/{workspace['id']}/cases/{legal_case['id']}"
                "/documents"
            )
            uploaded = require(
                await client.post(
                    base,
                    headers=auth_headers[0],
                    files={"file": ("agreement.pdf", original, "application/pdf")},
                ),
                201,
            )
            document_ids.append(UUID(str(uploaded["id"])))
            extraction = require(
                await client.post(
                    f"{base}/{uploaded['id']}/extract", headers=auth_headers[0]
                ),
                200,
            )
            retrieved = require(
                await client.get(
                    f"{base}/{uploaded['id']}/extraction", headers=auth_headers[0]
                ),
                200,
            )
            assert extraction == retrieved
            assert extraction["status"] == "COMPLETED"
            assert extraction["page_count"] == 2
            assert "[Page 1]" in str(extraction["text_content"])
            assert "[Page 2]" in str(extraction["text_content"])
            assert extraction["source_sha256_hash"] == hashlib.sha256(original).hexdigest()
            downloaded = await client.get(
                f"{base}/{uploaded['id']}/download", headers=auth_headers[0]
            )
            assert downloaded.status_code == 200
            assert downloaded.content == original
            assert hashlib.sha256(downloaded.content).hexdigest() == uploaded["sha256_hash"]

            assert (
                await client.get(
                    f"{base}/{uploaded['id']}/extraction", headers=auth_headers[1]
                )
            ).status_code == 404
            assert (
                await client.post(
                    f"{base}/{uploaded['id']}/extract", headers=auth_headers[1]
                )
            ).status_code == 404
            print("Phase 5 real HTTP E2E passed; temporary records and object will be removed.")
    finally:
        await cleanup(user_ids, workspace_ids, case_ids, document_ids)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    asyncio.run(run(args.base_url.rstrip("/")))


if __name__ == "__main__":
    main()
