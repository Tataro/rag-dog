import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, auth, documents, query
from .channels import line as line_channel
from .channels import telegram as telegram_channel
from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ragdog")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("starting rag-dog (embed=%s, gen=%s)", settings.embedding_model, settings.generation_model)
    yield
    log.info("shutting down")


app = FastAPI(title="rag-dog", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(query.router, prefix="/api/query", tags=["query"])
app.include_router(telegram_channel.router, prefix="/webhook/telegram", tags=["webhook"])
app.include_router(line_channel.router, prefix="/webhook/line", tags=["webhook"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
