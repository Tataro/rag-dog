# 0002 — Dense-only retrieval for v1

**Status**: Accepted
**Date**: 2026-05-21

## Context

The corpus is Thai + English. The embedding model is `bge-m3` (multilingual, 1024-dim).

Three retrieval strategies were considered:

- **Dense only** (cosine top-k=8 via pgvector HNSW).
- **Hybrid** (dense + Postgres FTS). Catches exact-keyword matches that dense embeddings miss — names, codes, technical terms. Postgres FTS does not tokenize Thai (no spaces); we would have to pre-tokenize with `pythainlp` before indexing.
- **Hybrid + reranker** (`bge-reranker-v2-m3`). Best precision, but adds ~1 GB resident and 200–500 ms per query.

## Decision

Ship **dense-only top-k=8** for v1.

## Consequences

- Simpler ingestion (no FTS index, no Thai tokenizer).
- Simpler retrieval (one query, no fusion).
- We will likely lose recall on exact-keyword queries — proper nouns, numeric codes, specific section titles.
- The upgrade trigger is "measured precision below ~70% on a small eval set built from real questions." When we hit that, layer hybrid first, then reranker if hybrid alone doesn't close the gap.
- Schema change for hybrid is non-breaking: add `text_search tsvector` generated column on `chunks`, build a `GIN` index, no migration of existing rows.

## Amended — 2026-06-02 (multi-user; see [0004](0004-multi-user-production-pivot.md) / [0005](0005-postgres-rls-tenant-isolation.md))

Retrieval is no longer global. Under RLS, every vector search is implicitly scoped to the asking User (a `user_id` predicate). HNSW is a *single* approximate graph over all Users' vectors, so a selective per-User filter can exhaust `ef_search` on other Users' rows and silently return fewer/worse results — quietly breaking the top-k=8 contract above as the corpus grows.

**Decision for v1**: keep a single global HNSW index and rely on **pgvector iterative index scans** (requires **pgvector ≥ 0.8**) to keep walking the graph until `k` matching rows are found. Pin the image to an explicit version — e.g. `pgvector/pgvector:0.8.0-pg16` — because the floating `:pg16` tag (used in `docker-compose.yml`) does not guarantee the pgvector version.

**Upgrade trigger**: when measured recall or p95 retrieval latency degrades past threshold as Users/corpus grow, partition `chunks` by `user_id` (declarative partitioning, HNSW per partition) so each query touches only one User's graph. That is a migration, hence deferred until measured need — same philosophy as the hybrid/reranker triggers above.
