"""Async client for Ollama's /api/chat endpoint."""
import httpx

from ..config import settings


async def chat(messages: list[dict], *, temperature: float = 0.2) -> str:
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=300.0) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "model": settings.generation_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return data["message"]["content"].strip()
