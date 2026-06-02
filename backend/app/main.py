import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, auth, documents, query
from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ragdog")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("starting rag-dog (embed=%s, gen=%s)", settings.embedding_model, settings.generation_model)
    from . import storage

    await storage.ensure_bucket()
    log.info("object storage ready (bucket=%s)", settings.s3_bucket)
    yield
    log.info("shutting down")


app = FastAPI(title="rag-dog", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(query.router, prefix="/api/query", tags=["query"])

# Telegram/Line bots are descoped for the multi-user launch (ADR 0004): they need a
# Google<->chat-id account-linking design. The channel code stays on disk, unwired.


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
