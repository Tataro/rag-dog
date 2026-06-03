# rag-dog

Multi-user, self-hosted RAG (Retrieval-Augmented Generation). Users sign in with Google, upload documents, and query them from a Next.js web app or a React Native (Expo) mobile app. Each user's documents and conversations are private — isolated at the database level with Postgres Row-Level Security. All inference runs on your own hardware via Ollama.

Developed on a MacBook M4 (36 GB); runs in production on self-hosted GPU servers.

## Stack

- **Web**: Next.js 16 (App Router, TS, Tailwind) — authenticated client
- **Mobile**: React Native + Expo (SDK 56) — see [`mobile/`](mobile/)
- **Backend**: Python 3.12 + FastAPI — authenticated HTTPS API
- **Auth**: Google sign-in, closed invite/admin allowlist, own session JWT
- **Vector DB**: Postgres 16 + pgvector (HNSW); per-user isolation via Row-Level Security
- **Embeddings**: `bge-m3` (multilingual, 1024-dim) via Ollama
- **Generation**: `qwen2.5:14b-instruct` (Q4, ~9 GB) via Ollama
- **Object storage**: MinIO (S3-compatible) for uploaded document files

> The original single-user assumption and the Telegram/Line bots have been superseded by the multi-user pivot — the bots are descoped pending a Google↔chat-id account-linking design. See [`docs/adr/`](docs/adr) (notably 0004) for the reasoning behind each choice.

## Quick start

```bash
# 1. Configuration
cp .env.example .env
# Set at minimum: GOOGLE_CLIENT_IDS (your Google OAuth web client ID),
# BOOTSTRAP_ADMIN_EMAILS (your email — becomes the first admin), and a strong
# SESSION_JWT_SECRET. DATABASE_URL is the owner/migration role; APP_DATABASE_URL
# is the least-privilege runtime role (ragdog_app) that RLS applies to.

# 2. Postgres (pgvector) + MinIO via Docker
docker compose up -d postgres minio

# 3. Ollama — install natively on macOS for GPU acceleration:
brew install ollama
brew services start ollama
# (or `docker compose up -d ollama` for CPU-only)

# 4. Pull models (~10 GB, one-time)
./ops/ollama/pull-models.sh

# 5. Backend — `alembic upgrade head` creates the users/allowed_emails tables,
#    the FORCE-RLS policies, and the least-privilege `ragdog_app` role.
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 6. Web app (in another terminal) — see "Web UI environment variables" below
cd frontend
pnpm install
pnpm dev   # http://localhost:3000

# 7. First login: sign in with a BOOTSTRAP_ADMIN_EMAILS account (auto-provisioned
#    as admin), then add colleagues' emails via the in-app Admin screen.
```

> In production the backend is a public, authenticated HTTPS API (Google-verified
> sign-in + the closed allowlist), not a localhost-only service. The old
> Cloudflare-Tunnel-for-bots setup (ADR 0003) was retired by ADR 0004.

## Layout

```
backend/        FastAPI service (auth + RLS + ingestion + retrieval + generation)
                channels/ holds the descoped Telegram/Line adapters (unwired)
frontend/       Next.js web app (authenticated)
mobile/         React Native + Expo app
docs/adr/       Architecture Decision Records
docs/superpowers/plans/   Implementation plans (backend, MinIO, web, mobile)
ops/            Ollama pull script, cloudflared config (legacy; bot path retired)
CONTEXT.md      Domain glossary
```

## Web UI environment variables

Create `frontend/.env.local` (never committed) with:

```
# URL of the FastAPI backend (no trailing slash)
NEXT_PUBLIC_API_BASE=http://localhost:8000

# Google OAuth 2.0 Web Client ID (from Google Cloud Console → APIs & Services → Credentials)
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<your-web-client-id>.apps.googleusercontent.com
```

> **Important:** the same web client ID must also appear in the backend's `GOOGLE_CLIENT_IDS` list (comma-separated) so the backend will accept tokens issued by it.

## Mobile app

A React Native (Expo SDK 56) client lives in [`mobile/`](mobile/). It provides Google Sign-In, document upload, and chat against the same FastAPI backend.

- A **dev build** is required (not Expo Go) — see [`mobile/README.md`](mobile/README.md) for setup.
- Configure `apiBase`, `googleWebClientId`, and `googleIosClientId` in `mobile/app.json` before building.

## Out of scope (for now)

OCR, hybrid retrieval, reranking, document tags, streaming responses, a production job queue, and the Telegram/Line bots (deferred pending a Google↔chat-id account-linking design). Multi-user auth, which was previously out of scope, is now implemented. See [`docs/superpowers/plans/`](docs/superpowers/plans) and [`docs/adr/`](docs/adr) for details.
