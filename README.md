# LEGAL MASTER

LEGAL MASTER is a local/private legal document workspace and the foundation for a document RAG platform. This repository now contains Phase 3: secure multi-tenant workspaces, role-based membership, and workspace-scoped legal cases on top of JWT authentication. Uploads, extraction, OCR, embeddings, retrieval, and chat are intentionally not implemented yet.

## Architecture

The project is a modular monolith. A React client calls one FastAPI application; PostgreSQL is the transactional store, Redis is reserved for background work, Qdrant is reserved for vectors, and documents use a storage-provider boundary backed by a private Docker volume in local development. LLM and embedding providers are represented by interfaces so core application code will not depend on one vendor.

See [docs/architecture.md](docs/architecture.md) for boundaries and dependency rules.

## Stack

- React 18, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, Axios
- Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL
- Argon2id via pwdlib, signed access/refresh JWTs, revocable refresh sessions
- Docker Compose, Redis 7, Qdrant
- pytest/pytest-asyncio and Vitest/Testing Library
- Declared for later extraction work: PyMuPDF, python-docx, pytesseract

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
- For host-only development: Python 3.12+ and Node.js 20+

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

Start only infrastructure with `docker compose up -d postgres redis qdrant`. If the backend runs on the host, change service hostnames in `.env` to `localhost` (for example, `postgres` to `localhost`). Then:

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

After adding or importing a SQLAlchemy model in `backend/app/models/__init__.py`, create a migration with `make migration name=create_users`. Review generated migrations before applying them. Phase 2 creates `users` and `refresh_tokens`; Phase 3 adds `workspaces`, `workspace_members`, and `cases`.

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

## Workspace and case retention

Workspace deletion is a soft delete: `is_active` becomes false while ownership and memberships remain available to authorized users. Case deletion is also a soft delete and sets both `is_active = false` and `status = ARCHIVED`. Archived records remain readable to workspace members so later legal-retention and audit features can build on stable historical relationships. Foreign keys use restrictive deletion rather than cascading through legal domain data.

An owner cannot be removed or demoted. Owners may remove any non-owner. Administrators may add users and remove members or viewers, but cannot remove owners/admins or change roles. Ownership transfer is intentionally deferred.

The workspace and case UI is available at `/workspaces`, `/workspaces/:workspaceId`, `/workspaces/:workspaceId/cases`, and `/workspaces/:workspaceId/cases/:caseId`.

## Roadmap

The next step is the document vault. Extraction, OCR, chunks/embeddings, Qdrant indexing, retrieval, local LLM integration, citations, analysis modes, bitemporal logic, editing, and security hardening should then be implemented in that order.
