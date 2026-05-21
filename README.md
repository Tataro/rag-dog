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
uploads/        Original document files (gitignored)
CONTEXT.md      Domain glossary
```

## Out of scope for v1

OCR, hybrid retrieval, reranking, multi-user auth, document tags, streaming responses, production job queue. See the [plan](.claude/../README.md) for details.
