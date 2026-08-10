from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.repositories.documents import DocumentRepository
from app.services.documents import validate_filename
from app.services.errors import DomainError
from app.storage.local import LocalStagedWrite, LocalStorageProvider, StorageError
from tests.phase3_helpers import add_member, create_account, create_workspace

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def make_docx() -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Override PartName="/word/document.xml"
 ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p/></w:body></w:document>""",
        )
    return buffer.getvalue()


async def create_case(
    client: AsyncClient,
    workspace_id: str,
    headers: dict[str, str],
    name: str = "Vault case",
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/cases",
        headers=headers,
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def upload_document(
    client: AsyncClient,
    workspace_id: str,
    case_id: str,
    headers: dict[str, str],
    *,
    filename: str = "contract.pdf",
    content: bytes = PDF_BYTES,
    mime_type: str = PDF_MIME,
):
    return await client.post(
        f"/api/v1/workspaces/{workspace_id}/cases/{case_id}/documents",
        headers=headers,
        files={"file": (filename, content, mime_type)},
    )


async def document_count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(Document)) or 0)


def stored_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


async def test_pdf_upload_list_get_download_hash_and_archive_retention(
    client: AsyncClient,
    session: AsyncSession,
    application,
) -> None:
    user, headers = await create_account(client, "pdf-owner@example.com")
    workspace = await create_workspace(client, headers)
    legal_case = await create_case(client, workspace["id"], headers)

    uploaded = await upload_document(client, workspace["id"], legal_case["id"], headers)
    assert uploaded.status_code == 201, uploaded.text
    metadata = uploaded.json()
    expected_hash = hashlib.sha256(PDF_BYTES).hexdigest()
    assert metadata == {
        "id": metadata["id"],
        "case_id": legal_case["id"],
        "original_filename": "contract.pdf",
        "mime_type": PDF_MIME,
        "file_size": len(PDF_BYTES),
        "sha256_hash": expected_hash,
        "status": "UPLOADED",
        "is_active": True,
        "created_by": user["id"],
        "created_at": metadata["created_at"],
        "updated_at": metadata["updated_at"],
    }
    assert "storage_key" not in metadata
    assert "stored_filename" not in metadata

    record = await session.scalar(select(Document).where(Document.id == UUID(metadata["id"])))
    assert record is not None
    assert record.stored_filename != record.original_filename
    assert record.sha256_hash == expected_hash
    storage: LocalStorageProvider = application.state.document_storage
    stored_path = storage.resolve_key(record.storage_key)
    assert stored_path.is_file()
    assert stored_path.read_bytes() == PDF_BYTES
    assert hashlib.sha256(stored_path.read_bytes()).hexdigest() == record.sha256_hash

    base = f"/api/v1/workspaces/{workspace['id']}/cases/{legal_case['id']}/documents"
    listed = await client.get(base, headers=headers)
    fetched = await client.get(f"{base}/{metadata['id']}", headers=headers)
    downloaded = await client.get(f"{base}/{metadata['id']}/download", headers=headers)
    assert [item["id"] for item in listed.json()] == [metadata["id"]]
    assert fetched.json() == metadata
    assert downloaded.status_code == 200
    assert downloaded.content == PDF_BYTES
    assert downloaded.headers["content-type"] == PDF_MIME
    assert downloaded.headers["content-length"] == str(len(PDF_BYTES))
    assert 'filename="contract.pdf"' in downloaded.headers["content-disposition"]

    archived = await client.delete(f"{base}/{metadata['id']}", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False
    retained_download = await client.get(f"{base}/{metadata['id']}/download", headers=headers)
    assert retained_download.status_code == 200
    assert retained_download.content == PDF_BYTES
    assert stored_path.is_file()


async def test_docx_upload_and_unicode_download_filename(
    client: AsyncClient,
) -> None:
    _, headers = await create_account(client, "docx-owner@example.com")
    workspace = await create_workspace(client, headers)
    legal_case = await create_case(client, workspace["id"], headers)
    content = make_docx()

    response = await upload_document(
        client,
        workspace["id"],
        legal_case["id"],
        headers,
        filename="合同.docx",
        content=content,
        mime_type=DOCX_MIME,
    )
    assert response.status_code == 201, response.text
    metadata = response.json()
    downloaded = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/cases/{legal_case['id']}/documents/"
        f"{metadata['id']}/download",
        headers=headers,
    )
    assert downloaded.content == content
    assert "filename*=UTF-8''" in downloaded.headers["content-disposition"]


@pytest.mark.parametrize(
    ("filename", "content", "mime_type", "expected_status"),
    [
        ("empty.pdf", b"", PDF_MIME, 422),
        ("payload.exe", PDF_BYTES, "application/octet-stream", 415),
        ("payload.pdf", PDF_BYTES, "application/octet-stream", 415),
        ("payload.pdf", b"MZ-not-a-pdf", PDF_MIME, 415),
        ("payload.docx", b"PK-not-a-docx", DOCX_MIME, 415),
        ("payload.docx", PDF_BYTES, DOCX_MIME, 415),
    ],
)
async def test_upload_rejects_invalid_content_and_metadata(
    client: AsyncClient,
    filename: str,
    content: bytes,
    mime_type: str,
    expected_status: int,
) -> None:
    _, headers = await create_account(client, f"invalid-{hash(filename + mime_type + str(content))}@example.com")
    workspace = await create_workspace(client, headers)
    legal_case = await create_case(client, workspace["id"], headers)

    response = await upload_document(
        client,
        workspace["id"],
        legal_case["id"],
        headers,
        filename=filename,
        content=content,
        mime_type=mime_type,
    )
    assert response.status_code == expected_status
    assert "storage" not in response.text.casefold()
    assert "path" not in response.text.casefold()


@pytest.mark.parametrize(
    "filename",
    [
        "../contract.pdf",
        "..\\contract.pdf",
        "/contract.pdf",
        f"{'a' * 252}.pdf",
        "e\u0301vidence.pdf",
    ],
)
async def test_upload_rejects_dangerous_filenames(
    client: AsyncClient,
    filename: str,
) -> None:
    _, headers = await create_account(client, f"filename-{abs(hash(filename))}@example.com")
    workspace = await create_workspace(client, headers)
    legal_case = await create_case(client, workspace["id"], headers)
    response = await upload_document(
        client,
        workspace["id"],
        legal_case["id"],
        headers,
        filename=filename,
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "filename",
    ["C:\\contract.pdf", "bad\x00name.pdf", "bad\nname.pdf"],
)
def test_filename_validator_rejects_values_normalized_by_multipart_parser(
    filename: str,
) -> None:
    with pytest.raises(DomainError) as error:
        validate_filename(filename)
    assert error.value.status_code == 422


async def test_upload_size_limit_is_stream_enforced(
    client: AsyncClient,
    application,
    session: AsyncSession,
) -> None:
    _, headers = await create_account(client, "oversize@example.com")
    workspace = await create_workspace(client, headers)
    legal_case = await create_case(client, workspace["id"], headers)
    application.state.settings.document_max_size_bytes = 8

    response = await upload_document(
        client,
        workspace["id"],
        legal_case["id"],
        headers,
        content=PDF_BYTES,
    )
    assert response.status_code == 413
    assert await document_count(session) == 0
    assert stored_files(application.state.document_storage.root) == []


@pytest.mark.parametrize(
    ("role", "upload_status", "archive_status"),
    [
        ("OWNER", 201, 200),
        ("ADMIN", 201, 200),
        ("MEMBER", 201, 200),
        ("VIEWER", 403, 403),
    ],
)
async def test_document_role_matrix(
    client: AsyncClient,
    role: str,
    upload_status: int,
    archive_status: int,
) -> None:
    _, owner_headers = await create_account(client, f"owner-{role}-docs@example.com")
    workspace = await create_workspace(client, owner_headers)
    legal_case = await create_case(client, workspace["id"], owner_headers)
    if role == "OWNER":
        actor_headers = owner_headers
    else:
        actor, actor_headers = await create_account(client, f"actor-{role}-docs@example.com")
        await add_member(client, workspace["id"], owner_headers, actor["email"], role)

    owner_upload = await upload_document(client, workspace["id"], legal_case["id"], owner_headers)
    document = owner_upload.json()
    base = f"/api/v1/workspaces/{workspace['id']}/cases/{legal_case['id']}/documents"
    assert (await client.get(base, headers=actor_headers)).status_code == 200
    assert (await client.get(f"{base}/{document['id']}", headers=actor_headers)).status_code == 200
    assert (await client.get(f"{base}/{document['id']}/download", headers=actor_headers)).status_code == 200

    actor_upload = await upload_document(
        client,
        workspace["id"],
        legal_case["id"],
        actor_headers,
        filename=f"{role.casefold()}.pdf",
    )
    assert actor_upload.status_code == upload_status
    archived = await client.delete(f"{base}/{document['id']}", headers=actor_headers)
    assert archived.status_code == archive_status


async def test_cross_tenant_and_id_mismatch_requests_return_not_found(
    client: AsyncClient,
) -> None:
    _, headers_a = await create_account(client, "tenant-a-docs@example.com")
    _, headers_b = await create_account(client, "tenant-b-docs@example.com")
    workspace_a = await create_workspace(client, headers_a, "Workspace A")
    workspace_b = await create_workspace(client, headers_b, "Workspace B")
    case_a = await create_case(client, workspace_a["id"], headers_a, "Case A")
    case_b = await create_case(client, workspace_b["id"], headers_b, "Case B")
    document_a = (await upload_document(client, workspace_a["id"], case_a["id"], headers_a)).json()
    document_b = (await upload_document(client, workspace_b["id"], case_b["id"], headers_b)).json()

    base_b = f"/api/v1/workspaces/{workspace_b['id']}/cases/{case_b['id']}/documents"
    attacks = [
        client.get(base_b, headers=headers_a),
        client.get(f"{base_b}/{document_b['id']}", headers=headers_a),
        client.get(f"{base_b}/{document_b['id']}/download", headers=headers_a),
        client.delete(f"{base_b}/{document_b['id']}", headers=headers_a),
        client.get(
            f"/api/v1/workspaces/{workspace_a['id']}/cases/{case_a['id']}/documents/{document_b['id']}",
            headers=headers_a,
        ),
        client.get(
            f"/api/v1/workspaces/{workspace_a['id']}/cases/{case_b['id']}/documents/{document_b['id']}",
            headers=headers_a,
        ),
        client.get(
            f"/api/v1/workspaces/{workspace_b['id']}/cases/{case_a['id']}/documents/{document_a['id']}",
            headers=headers_b,
        ),
        client.get(
            f"/api/v1/workspaces/{workspace_a['id']}/cases/{case_a['id']}/documents/{document_a['id']}",
            headers=headers_b,
        ),
    ]
    responses = [await request for request in attacks]
    assert [response.status_code for response in responses] == [404] * len(responses)


@pytest.mark.parametrize("malicious_key", ["../../etc/passwd", "../outside", "/absolute/path"])
async def test_download_rejects_manipulated_storage_keys(
    client: AsyncClient,
    session: AsyncSession,
    malicious_key: str,
) -> None:
    _, headers = await create_account(client, f"key-{abs(hash(malicious_key))}@example.com")
    workspace = await create_workspace(client, headers)
    legal_case = await create_case(client, workspace["id"], headers)
    metadata = (await upload_document(client, workspace["id"], legal_case["id"], headers)).json()
    record = await session.scalar(select(Document).where(Document.id == UUID(metadata["id"])))
    assert record is not None
    record.storage_key = malicious_key
    await session.commit()

    response = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/cases/{legal_case['id']}/documents/"
        f"{metadata['id']}/download",
        headers=headers,
    )
    assert response.status_code == 404
    assert malicious_key not in response.text


async def test_storage_failure_leaves_no_row_or_partial_file(
    client: AsyncClient,
    session: AsyncSession,
    application,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await create_account(client, "storage-failure@example.com")
    workspace = await create_workspace(client, headers)
    legal_case = await create_case(client, workspace["id"], headers)
    original_write = LocalStagedWrite.write

    def failing_write(self, chunk: bytes) -> None:
        original_write(self, chunk[:3])
        raise StorageError("simulated")

    monkeypatch.setattr(LocalStagedWrite, "write", failing_write)
    response = await upload_document(client, workspace["id"], legal_case["id"], headers)
    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to store document"}
    assert await document_count(session) == 0
    assert stored_files(application.state.document_storage.root) == []


async def test_database_failure_removes_published_file_and_row(
    client: AsyncClient,
    session: AsyncSession,
    application,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await create_account(client, "database-failure@example.com")
    workspace = await create_workspace(client, headers)
    legal_case = await create_case(client, workspace["id"], headers)

    async def failing_create(self, document):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(DocumentRepository, "create", failing_create)
    response = await upload_document(client, workspace["id"], legal_case["id"], headers)
    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to save document metadata"}
    assert await document_count(session) == 0
    assert stored_files(application.state.document_storage.root) == []
