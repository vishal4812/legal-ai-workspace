from __future__ import annotations

import io
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import pymupdf
from docx import Document as WordDocument
from httpx import AsyncClient

from tests.phase3_helpers import create_account, create_workspace

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def make_pdf(*pages: str | None, draw_image_shape: bool = False) -> bytes:
    pdf = pymupdf.open()
    for text in pages or (None,):
        page = pdf.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=11)
        if draw_image_shape:
            page.draw_rect(pymupdf.Rect(72, 90, 180, 150), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    content = pdf.tobytes()
    pdf.close()
    return content


def make_docx(
    *,
    heading: str | None = None,
    paragraphs: tuple[str, ...] = (),
    table: tuple[tuple[str, ...], ...] = (),
) -> bytes:
    document = WordDocument()
    if heading is not None:
        document.add_heading(heading, level=1)
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if table:
        word_table = document.add_table(rows=len(table), cols=len(table[0]))
        for row_index, row in enumerate(table):
            for column_index, value in enumerate(row):
                word_table.cell(row_index, column_index).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_malformed_docx() -> bytes:
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
        archive.writestr("word/document.xml", "<not-valid-word-xml")
    return buffer.getvalue()


async def create_case(
    client: AsyncClient,
    workspace_id: str,
    headers: dict[str, str],
    name: str = "Extraction case",
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/cases",
        headers=headers,
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_document_context(
    client: AsyncClient,
    email: str,
    *,
    filename: str = "agreement.pdf",
    content: bytes | None = None,
    mime_type: str = PDF_MIME,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, str],
    bytes,
]:
    user, headers = await create_account(client, email)
    workspace = await create_workspace(client, headers)
    legal_case = await create_case(client, workspace["id"], headers)
    original = content if content is not None else make_pdf("Agreement text")
    response = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/cases/{legal_case['id']}/documents",
        headers=headers,
        files={"file": (filename, original, mime_type)},
    )
    assert response.status_code == 201, response.text
    return user, workspace, legal_case, response.json(), headers, original


def document_base(workspace: dict[str, Any], legal_case: dict[str, Any]) -> str:
    return f"/api/v1/workspaces/{workspace['id']}/cases/{legal_case['id']}/documents"
