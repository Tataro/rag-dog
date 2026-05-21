# 0001 — Postgres + pgvector over a dedicated vector DB

**Status**: Accepted
**Date**: 2026-05-21

## Context

This is a single-user POC running on a MacBook M4 today, with a vague plan to move to a bigger GPU/CPU box later. We need a vector store for embeddings (1024-dim, from `bge-m3`) and a regular relational store for documents, chunks, conversations, messages.

Candidates:

- **Postgres + pgvector** — one DB, transactional, HNSW indexing, scales to millions of vectors.
- **Qdrant** — purpose-built, strong recall and filtering, separate service.
- **SQLite + sqlite-vec** — zero infra, but bots run as separate processes and would have to coordinate on a single file.
- **ChromaDB** — easiest dev ergonomics, but its production story is the thinnest of the four.

## Decision

Use **Postgres 16 with the pgvector extension** for both relational data and embeddings.

## Consequences

- One container, one connection pool, one client library, one backup story.
- Document metadata and embedding live in the same transaction — no two-phase write issues when ingesting.
- HNSW (`m=16, ef_construction=64`) gives us ~95% recall on personal-corpus sizes (≤1M vectors) with sub-100ms query latency.
- We give up the absolute best ANN performance at the scale of tens of millions of vectors. If we ever hit that, we migrate to Qdrant — the embedding column and chunk metadata move out of Postgres but the rest of the schema stays.
- We use `pgvector/pgvector:pg16` so the extension is preinstalled.
