from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://ragdog:ragdog@localhost:5432/ragdog"

    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    generation_model: str = "qwen2.5:14b-instruct"
    embedding_dim: int = 1024  # bge-m3 dimensionality

    chunk_size_tokens: int = 1000
    chunk_overlap_tokens: int = 100
    retrieval_top_k: int = 8
    history_turns: int = 5
    citations_limit: int = 3

    upload_dir: Path = Path("./uploads")

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_allowed_chat_ids: str = ""  # comma-separated

    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_allowed_user_ids: str = ""  # comma-separated

    cors_origins: str = "http://localhost:3000"

    @property
    def telegram_allowlist(self) -> set[str]:
        return {x.strip() for x in self.telegram_allowed_chat_ids.split(",") if x.strip()}

    @property
    def line_allowlist(self) -> set[str]:
        return {x.strip() for x in self.line_allowed_user_ids.split(",") if x.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
