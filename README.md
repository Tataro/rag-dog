# rag-dog

Single-user, local-first RAG (Retrieval-Augmented Generation). Upload documents through a Next.js web UI; query them from the web, Telegram, or Line. All inference runs locally via Ollama.

Designed for a MacBook M4 (36 GB), portable to a bigger GPU box later.

## Stack

- **Frontend**: Next.js 15 (App Router, TS, Tailwind) — localhost only
- **Backend**: Python 3.12 + FastAPI
- **Vector DB**: Postgres 16 + pgvector (HNSW)
- **Embeddings**: `bge-m3` (multilingual, 1024-dim) via Ollama
- **Generation**: `qwen2.5:14b-instruct` (Q4, ~9 GB) via Ollama
- **Bots**: Telegram + Line, exposed via Cloudflare Tunnel (webhooks only)
- **Object storage**: MinIO (S3-compatible) for uploaded document files

See [`docs/adr/`](docs/adr) for the reasoning behind each choice.

## Quick start

```bash
# 1. Configuration
cp .env.example .env
# Edit .env if you want different ports/credentials.

# 2. Postgres (with pgvector) via Docker
docker compose up -d postgres

# 3. Ollama — install natively on macOS for GPU acceleration:
brew install ollama
brew services start ollama
# (or `docker compose up -d ollama` for CPU-only)

# 4. Pull models (~10 GB, one-time)
./ops/ollama/pull-models.sh

# 5. Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 6. Frontend (in another terminal)
cd frontend
pnpm install
pnpm dev   # http://localhost:3000

# 7. Cloudflare Tunnel — only when you want bots reachable
# See ops/cloudflared/README.md
```

## Layout

```
backend/        FastAPI service (ingestion + retrieval + generation + channels)
frontend/       Next.js web UI
docs/adr/       Architecture Decision Records
ops/            Cloudflare Tunnel config, Ollama pull script
uploads/        (removed) original document files now stored in MinIO object storage
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

## Out of scope for v1

OCR, hybrid retrieval, reranking, multi-user auth, document tags, streaming responses, production job queue. See the [plan](.claude/../README.md) for details.
