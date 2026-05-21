"""Thin async client for Ollama's /api/embed endpoint.

Ollama exposes embeddings at POST /api/embed with `{model, input: str | list[str]}`.
We batch chunks ~32 at a time to keep request bodies modest.
"""
from collections.abc import Iterable

import httpx

from ..config import settings

_BATCH = 32


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    out: list[list[float]] = []
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=120.0) as client:
        for batch in _batched(texts, _BATCH):
            resp = await client.post(
                "/api/embed",
                json={"model": settings.embedding_model, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()
            out.extend(data["embeddings"])
    return out


async def embed_text(text: str) -> list[float]:
    [vec] = await embed_texts([text])
    return vec


def _batched(items: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]
