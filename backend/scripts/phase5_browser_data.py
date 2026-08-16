from __future__ import annotations

import argparse
import asyncio
from importlib.metadata import version
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.database import Database
from app.models.document import Document
from app.models.document_extraction import DocumentExtraction, ExtractionStatus
from app.models.case import Case
from app.models.user import User
from app.models.workspace import Workspace
from scripts.phase5_http_e2e import cleanup


async def mark_failed(document_id: UUID) -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        async with database.session_factory() as session:
            document = await session.scalar(
                select(Document).where(Document.id == document_id)
            )
            if document is None:
                raise RuntimeError("Browser fixture document was not found")
            package = "PyMuPDF" if document.mime_type == "application/pdf" else "python-docx"
            extractor_type = "pymupdf" if package == "PyMuPDF" else "python-docx"
            session.add(
                DocumentExtraction(
                    document_id=document.id,
                    extractor_type=extractor_type,
                    extractor_version=version(package),
                    status=ExtractionStatus.FAILED,
                    text_content="",
                    character_count=0,
                    page_count=None,
                    source_sha256_hash=document.sha256_hash,
                    error_code="TRANSIENT_TEST_FAILURE",
                    error_message="A transient extraction failure was recorded",
                )
            )
            await session.commit()
    finally:
        await database.dispose()


async def mark_processing(document_id: UUID) -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        async with database.session_factory() as session:
            document = await session.scalar(
                select(Document).where(Document.id == document_id)
            )
            if document is None:
                raise RuntimeError("Browser fixture document was not found")
            package = "PyMuPDF" if document.mime_type == "application/pdf" else "python-docx"
            extractor_type = "pymupdf" if package == "PyMuPDF" else "python-docx"
            session.add(
                DocumentExtraction(
                    document_id=document.id,
                    extractor_type=extractor_type,
                    extractor_version=version(package),
                    status=ExtractionStatus.PROCESSING,
                    text_content="",
                    character_count=0,
                    page_count=None,
                    source_sha256_hash=document.sha256_hash,
                )
            )
            await session.commit()
    finally:
        await database.dispose()


async def cleanup_suffix(suffix: str) -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        async with database.session_factory() as session:
            emails = [
                f"phase5-browser-{role}-{suffix}@example.com"
                for role in ("owner", "admin", "member", "viewer", "outsider")
            ]
            user_ids = list(
                (await session.scalars(select(User.id).where(User.email.in_(emails)))).all()
            )
            workspace_ids = list(
                (
                    await session.scalars(
                        select(Workspace.id).where(Workspace.owner_id.in_(user_ids))
                    )
                ).all()
            )
            case_ids = list(
                (
                    await session.scalars(
                        select(Case.id).where(Case.workspace_id.in_(workspace_ids))
                    )
                ).all()
            )
            document_ids = list(
                (
                    await session.scalars(
                        select(Document.id).where(Document.case_id.in_(case_ids))
                    )
                ).all()
            )
    finally:
        await database.dispose()
    await cleanup(user_ids, workspace_ids, case_ids, document_ids)


def uuid_values(values: list[str]) -> list[UUID]:
    return [UUID(value) for value in values]


async def run(args: argparse.Namespace) -> None:
    if args.command == "mark-failed":
        await mark_failed(UUID(args.document_id))
        return
    if args.command == "mark-processing":
        await mark_processing(UUID(args.document_id))
        return
    if args.command == "cleanup-suffix":
        await cleanup_suffix(args.suffix)
        return
    await cleanup(
        uuid_values(args.user_id),
        uuid_values(args.workspace_id),
        uuid_values(args.case_id),
        uuid_values(args.document_id),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    mark = subparsers.add_parser("mark-failed")
    mark.add_argument("--document-id", required=True)
    processing = subparsers.add_parser("mark-processing")
    processing.add_argument("--document-id", required=True)
    clean = subparsers.add_parser("cleanup")
    clean.add_argument("--user-id", action="append", default=[])
    clean.add_argument("--workspace-id", action="append", default=[])
    clean.add_argument("--case-id", action="append", default=[])
    clean.add_argument("--document-id", action="append", default=[])
    suffix_cleanup = subparsers.add_parser("cleanup-suffix")
    suffix_cleanup.add_argument("--suffix", required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
