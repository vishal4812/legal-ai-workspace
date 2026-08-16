# LEGAL MASTER

LEGAL MASTER is a local/private legal document workspace. This repository contains Phase 7: deterministic legal-text chunking, local CPU embeddings, tenant-filtered Qdrant indexing, and semantic vector retrieval, built on the Phase 6 PDF/DOCX extraction and OCR pipeline. Phase 7 provides ranked source chunks only; RAG answer generation, LLM APIs, chat, legal advice, and legal analysis are not implemented.

## Architecture

The project is a modular monolith. A React client calls one FastAPI application; PostgreSQL is the transactional and canonical chunk store, Redis is reserved for future background work, Qdrant stores tenant-filtered chunk vectors, and documents use a storage-provider boundary backed by a private Docker volume. Local embedding and vector adapters remain behind provider interfaces.

See [docs/architecture.md](docs/architecture.md) for boundaries and dependency rules.

## Stack

- React 18, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, Axios
- Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL
- Argon2id via pwdlib, signed access/refresh JWTs, revocable refresh sessions
- Docker Compose, Redis 7, Qdrant
- pytest/pytest-asyncio and Vitest/Testing Library
- PyMuPDF, python-docx, Pillow, pytesseract, and local Tesseract OCR
- FastEmbed CPU/ONNX local embeddings and Qdrant vector search

## Repository layout

```text
backend/          FastAPI modular monolith, migrations, and backend tests
frontend/         React application and frontend tests
infrastructure/   Infrastructure notes and future deployment assets
docs/             Architecture documentation
scripts/          Developer verification scripts
docker-compose.yml
Makefile
```

## Prerequisites

- Docker Engine with Docker Compose v2
- Make (optional; commands can be run directly)
- For host-only development: Python 3.12+, Node.js 20+, and Tesseract with every configured `OCR_LANG` installed

## Configure and run with Docker

```bash
cp .env.example .env
# Replace POSTGRES_PASSWORD and JWT_SECRET in .env.
make up
docker compose ps
curl http://localhost:8000/health
```

The UI is available at <http://localhost:5173>, FastAPI at <http://localhost:8000>, and OpenAPI at <http://localhost:8000/docs>. Infrastructure ports are bound to loopback only. `make logs` follows logs and `make down` stops the stack while preserving named volumes. Use `docker compose down -v` only when you deliberately want to delete local service data.

## Run services on the host

Start only infrastructure with `docker compose up -d postgres redis qdrant`. If the backend runs on the host, change PostgreSQL/Redis service hostnames in `.env` to `localhost`. Phase 7 intentionally does not publish Qdrant to the host; host-only backend development therefore needs an explicit local-only Compose override for `127.0.0.1:6333:6333` or a separately secured local Qdrant. Never publish it on a public interface. Then:

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd backend && .venv/bin/uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

## Tests and checks

```bash
make test
./scripts/check.sh
```

For host environments, run `cd backend && .venv/bin/pytest` and `cd frontend && npm test -- --run && npm run build`.

## Database migrations

Alembic uses the same `DATABASE_URL` as the application. Apply migrations with:

```bash
make migrate
```

After adding or importing a SQLAlchemy model in `backend/app/models/__init__.py`, create a migration with `make migration name=create_users`. Review generated migrations before applying them. Phase 2 creates `users` and `refresh_tokens`; Phase 3 adds workspaces/cases; Phase 4 adds documents; Phase 5 adds document extractions; Phase 6 adds structured OCR provenance; Phase 7 migration `0006_document_chunking_and_indexing.py` adds `document_chunks`, one `document_indexes` row per document, and the `indexing_status` enum.

## Authentication

The authentication API is available under `/api/v1/auth`:

- `POST /register`
- `POST /login`
- `POST /refresh`
- `POST /logout`
- `GET /me`

Access tokens are short-lived and held in frontend memory. Refresh tokens are rotated and sent to browsers in an HttpOnly, SameSite=Lax cookie; only their unique JWT identifier is persisted in PostgreSQL. Non-browser API clients may submit a refresh token in the refresh/logout request body.

The cookie is marked Secure outside local/test environments. A future cross-site deployment must pair any relaxed SameSite policy with explicit CSRF protection.

## Configuration and security

Pydantic validates settings at backend startup. `DATABASE_URL` and `JWT_SECRET` are required; `JWT_SECRET` must be at least 32 characters. `.env`, local documents, database/vector data, logs, and model artifacts are ignored by Git. Do not serve document-volume paths through the web server. Future storage and vector endpoints must reuse the workspace/case authorization boundary and emit audit events.

### Document storage configuration

- `DOCUMENT_STORAGE_PATH` selects the private backend-only storage root (Docker uses `/data/documents`).
- `DOCUMENT_MAX_SIZE_BYTES` limits each upload and defaults to `52428800` bytes (50 MiB).
- Docker Compose mounts the named `document_storage` volume only into the backend. The frontend/nginx service cannot serve it.

### Local OCR configuration

- `OCR_ENABLED=true` enables the PDF fallback without affecting direct PDF or DOCX extraction when disabled/unavailable.
- `OCR_LANG=eng` is passed exactly to Tesseract after every requested `+`-separated language is verified as installed. There is no silent language fallback.
- `OCR_DPI=200` controls page rendering (validated from 100–400 DPI). The default balances typed legal-text accuracy and memory use.
- `OCR_MAX_PAGES=100` limits the total pages in a PDF entering the OCR-enabled pipeline. Extraction fails rather than silently omitting pages.
- `OCR_TIMEOUT_SECONDS=120` is one total OCR budget per document, including engine checks, queueing, rendering, and recognition.
- `OCR_MAX_IMAGE_PIXELS=25000000` rejects unusually large rendered pages before allocating their image.
- `OCR_MAX_CONCURRENCY=1` bounds simultaneous Tesseract processes in this synchronous MVP.

The backend image installs Debian's `tesseract-ocr` package (English plus orientation/script detection in the current image). Verify a built image with `docker compose run --rm --no-deps backend tesseract --version` and `docker compose run --rm --no-deps backend tesseract --list-langs`.

### Local indexing configuration

- `CHUNK_SIZE=800`, `CHUNK_OVERLAP=120`, and `CHUNK_MIN_SIZE=100` count deterministic non-whitespace lexemes. The selected model accepts substantially more than 800 model tokens, preventing silent truncation of default chunks.
- `EMBEDDING_PROVIDER=local` is the only Phase 7 provider. `EMBEDDING_MODEL=jinaai/jina-embeddings-v2-small-en` runs through FastEmbed/ONNX on CPU and produces 512-dimensional vectors. `EMBEDDING_DIMENSION=512` is checked against FastEmbed model metadata and every emitted vector.
- `EMBEDDING_BATCH_SIZE=32` and `EMBEDDING_MAX_CONCURRENCY=1` bound inference. `QDRANT_UPSERT_BATCH_SIZE=64` bounds vector writes.
- `EMBEDDING_CACHE_PATH=/data/models` uses a backend-only named Docker volume. The first index/search downloads the approximately 120 MiB model; later requests and container recreations reuse the cache. No model binary is committed or exposed by the frontend.
- `QDRANT_COLLECTION_NAME=legal_master_document_chunks` and `QDRANT_TIMEOUT_SECONDS=30` configure the private vector adapter. A missing collection is created with cosine distance and the provider dimension. An incompatible existing collection fails safely and is never destroyed or recreated automatically.

Qdrant has no host-published port in Docker Compose. Only services on the private Compose network can reach it, and the application exposes vectors solely through authenticated, workspace-authorized APIs.

## Secure Document Vault

Every document belongs to exactly one case, and every request resolves the complete `User -> Membership -> Workspace -> Case -> Document` chain. Non-members, cross-tenant IDs, and workspace/case/document mismatches return 404. OWNER, ADMIN, and MEMBER can upload and archive; VIEWER can list, view metadata, and download.

The nested API is:

- `POST /api/v1/workspaces/{workspace_id}/cases/{case_id}/documents`
- `GET /api/v1/workspaces/{workspace_id}/cases/{case_id}/documents`
- `GET /api/v1/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}`
- `GET /api/v1/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}/download`
- `DELETE /api/v1/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}`

Uploads accept PDF and DOCX only. The backend checks extension, declared MIME type, PDF magic bytes, or the required DOCX OOXML ZIP members/content type. It streams to a private temporary object in bounded chunks, calculates SHA-256 during that stream, atomically publishes a UUID-only storage key, and then commits metadata. Storage failures create no row; database failures remove the published object. Original filenames are validated metadata and are never storage paths.

Downloads are authenticated backend streams with safe `Content-Type`, `Content-Length`, `Content-Disposition`, and `X-Content-Type-Options` headers. Storage keys are never returned by the API and local key resolution uses resolved-path containment under the configured root.

The UI is available at `/workspaces/:workspaceId/cases/:caseId/documents`. It provides selection validation, progress, loading/error/empty states, metadata and SHA-256 display, download, and role-aware archive controls.

## Document Text Extraction and OCR

Phase 6 extracts text locally and synchronously through `DocumentExtractionService`. The service opens an immutable original through `StorageProvider`, selects `PDFExtractor` or `DOCXExtractor`, normalizes parser noise, and persists one current `document_extractions` row. Routes contain no parsing or direct filesystem access, so the service remains independently callable by a future background worker.

The nested extraction API is:

- `POST /api/v1/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}/extract`
- `GET /api/v1/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}/extraction`

OWNER, ADMIN, and MEMBER can trigger and view extraction. VIEWER can view an existing extraction but cannot trigger or retry it. The existing workspace/case/document authorization chain returns 404 for non-members and ID mismatches.

Each document has at most one extraction with a `PENDING -> PROCESSING -> COMPLETED` or `PROCESSING -> FAILED` lifecycle. A completed extraction is returned idempotently; a failed extraction can be retried in the same row; pending or processing work returns 409. Failures persist a bounded safe code/message and API responses never expose parser traces, storage keys, or filesystem paths. `source_sha256_hash` ties the result to the immutable Phase 4 original.

PyMuPDF first extracts each PDF page. A page avoids OCR only when its normalized parser output has at least 20 non-whitespace characters, 10 alphabetic characters, a 90% printable-character ratio, and a 50% alphanumeric-character ratio. This documented deterministic heuristic rejects empty pages, isolated page numbers/headers, and obvious parser noise without interpreting legal meaning.

Only insufficient pages are rendered, one at a time, at `OCR_DPI` and sent as in-memory RGB images through `OCRProvider -> TesseractOCRProvider`. Normal PDFs remain direct-only; image PDFs use OCR; mixed PDFs retain direct text on sufficient pages and OCR only scanned/insufficient pages. Page images are released before the next page and are never published or exposed. Persisted PDF text uses deterministic `[Page N]` markers, and `page_count` always records the actual PDF page count, including mixed documents. `python-docx` remains direct-only; DOCX is never rendered or OCRed.

For completed results, `parser_metadata.method` is `direct_text`, `ocr`, or `mixed`. PDF metadata records the actual engine/version, language and DPI when OCR runs, plus one-based `direct_text_pages` and `ocr_pages`. A page-limit failure uses `undetermined` because it is rejected before page content is inspected. OCR-only results use extractor type `tesseract`; mixed results use `pymupdf+tesseract`. Versions are read from installed packages/processes rather than fabricated.

OCR uses the existing `PENDING -> PROCESSING -> COMPLETED` or `PROCESSING -> FAILED` lifecycle. Completed results remain idempotent, failed OCR retries reset and reuse the same row, and pending/processing work conflicts. An OCR page-limit failure never creates a partial completed result. The original PDF is opened read-only: its object bytes, storage key, document metadata, and SHA-256 are not changed.

Stable OCR-related failure codes are `OCR_DISABLED`, `OCR_UNAVAILABLE`, `OCR_LANGUAGE_UNAVAILABLE`, `OCR_TIMEOUT`, `OCR_PAGE_LIMIT_EXCEEDED`, `OCR_IMAGE_LIMIT_EXCEEDED`, `OCR_RENDER_FAILED`, and `OCR_PROCESSING_FAILED`. Corrupt PDFs use `DOCUMENT_CORRUPTED`; storage and unexpected extraction failures retain the existing bounded codes. Only safe messages are persisted/returned—never parser output, command lines, storage keys, paths, document contents, or stack traces.

Normalization converts CRLF/CR line endings to LF, removes null characters, collapses horizontal whitespace and excessive blank lines, and trims line edges. It does not summarize, paraphrase, spell-correct, deduplicate, or otherwise alter legal wording, punctuation, or numbers. Extracted text is read-only in the UI at `/workspaces/:workspaceId/cases/:caseId/documents/:documentId/extraction`.

## Deterministic indexing and semantic search

Phase 7 extends only completed, current extractions:

```text
Normalized extraction -> deterministic chunks -> PostgreSQL
                                      -> local batch embeddings
                                      -> tenant-tagged Qdrant points
Authenticated query -> local query embedding -> filtered Qdrant search
                    -> authorized canonical PostgreSQL chunks
```

The chunker preserves character content and document order, prefers page/paragraph/sentence boundaries, never splits a word, and uses a 120-lexeme overlap. `[Page N]` markers remain in chunk content when they fall within a chunk, while `page_start`/`page_end` remain queryable metadata. Each chunk stores SHA-256 over its exact persisted UTF-8 content, counts, extraction/document references, and safe source provenance. Canonical text is not duplicated into Qdrant.

Each document has one `document_indexes` lifecycle row: `PENDING -> PROCESSING -> COMPLETED` or `PROCESSING -> FAILED`. A current completed index is returned idempotently. A failed row is reset and reused; changed extraction text causes controlled chunk/vector replacement. PostgreSQL state becomes non-completed before vector replacement, and search returns only chunks whose canonical row, completed index SHA, payload hash, workspace, case, and document all agree. Partial/stale Qdrant points therefore remain unsearchable during failures; no distributed transaction is claimed.

Index API:

- `POST /api/v1/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}/index`
- `GET /api/v1/workspaces/{workspace_id}/cases/{case_id}/documents/{document_id}/index`

Search API:

- `POST /api/v1/workspaces/{workspace_id}/search` with `query`, optional `case_id`, and `top_k` from 1–50.

OWNER, ADMIN, and MEMBER may trigger/retry indexing; VIEWER may only view its status. All workspace roles may search. Workspace authorization occurs before query embedding/vector access, case IDs are resolved inside the authorized workspace, and every Qdrant query includes a mandatory `workspace_id` filter. Non-members and nested ID mismatches receive 404. Results are ranked canonical chunks with similarity score and page metadata—not generated answers.

Archived documents remain retained/readable under the existing legal-retention behavior; an already indexed archived document remains searchable by authorized workspace members. Phase 7 does not add deletion or retention cleanup.

Stable provider/indexing errors include `EMBEDDING_MODEL_UNAVAILABLE`, `EMBEDDING_DIMENSION_MISMATCH`, `EMBEDDING_INVALID_VECTOR`, `QDRANT_UNAVAILABLE`, `QDRANT_COLLECTION_INCOMPATIBLE`, `QDRANT_DIMENSION_MISMATCH`, `QDRANT_DISTANCE_MISMATCH`, `QDRANT_INDEXING_FAILED`, `QDRANT_POINT_COUNT_MISMATCH`, and `INDEXING_FAILED`. Responses/logs do not expose vectors, chunk/document text, storage keys, local paths, raw model/Qdrant exceptions, credentials, or tokens.

## Workspace, case, and document retention

Workspace deletion is a soft delete: `is_active` becomes false while ownership and memberships remain available to authorized users. Case deletion is also a soft delete and sets both `is_active = false` and `status = ARCHIVED`. Archived records remain readable to workspace members so later legal-retention and audit features can build on stable historical relationships. Foreign keys use restrictive deletion rather than cascading through legal domain data.

An owner cannot be removed or demoted. Owners may remove any non-owner. Administrators may add users and remove members or viewers, but cannot remove owners/admins or change roles. Ownership transfer is intentionally deferred.

Document DELETE is an archive operation: it sets `is_active=false`. The metadata row and original binary remain retained, listed, traceable, and downloadable to authorized members. Permanent deletion and automated retention cleanup are not implemented.

The workspace and case UI is available at `/workspaces`, `/workspaces/:workspaceId`, `/workspaces/:workspaceId/cases`, and `/workspaces/:workspaceId/cases/:caseId`.

## Phase boundary

Phase 7 provides vector retrieval only. It does not implement RAG answer generation, LLM chat, prompt pipelines, citations generated by an LLM, legal advice, legal analysis, summarization, reranking with an LLM, or any paid/cloud AI API. Phase 8 has not started.
