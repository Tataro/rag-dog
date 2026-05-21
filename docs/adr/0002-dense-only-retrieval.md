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
