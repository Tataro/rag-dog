from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Admin/owner connection: runs migrations and admin/maintenance work. Superuser.
    database_url: str = "postgresql+asyncpg://ragdog:ragdog@localhost:5432/ragdog"
    # Runtime app connection: a least-privilege, NON-superuser, NON-BYPASSRLS role so
    # that Row-Level Security actually applies to request-path queries (see ADR 0005).
    app_database_url: str = "postgresql+asyncpg://ragdog_app:ragdog_app@localhost:5432/ragdog"

    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    generation_model: str = "qwen2.5:14b-instruct"
    embedding_dim: int = 1024  # bge-m3 dimensionality

    chunk_size_tokens: int = 1000
    chunk_overlap_tokens: int = 100
    retrieval_top_k: int = 8
    history_turns: int = 5
    citations_limit: int = 3

    # Object storage (MinIO / S3-compatible) for uploaded Document files.
    s3_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str = "ragdog"
    s3_secret_key: str = "ragdog-secret"
    s3_bucket: str = "ragdog-documents"

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_allowed_chat_ids: str = ""  # comma-separated

    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_allowed_user_ids: str = ""  # comma-separated

    cors_origins: str = "http://localhost:3000"

    google_client_ids: str = ""  # comma-separated OAuth client IDs (web + mobile) accepted as token audience
    session_jwt_secret: str = "dev-insecure-change-me"
    session_jwt_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days
    bootstrap_admin_emails: str = ""  # comma-separated; implicitly allowed + admin on first login

    @property
    def telegram_allowlist(self) -> set[str]:
        return {x.strip() for x in self.telegram_allowed_chat_ids.split(",") if x.strip()}

    @property
    def line_allowlist(self) -> set[str]:
        return {x.strip() for x in self.line_allowed_user_ids.split(",") if x.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def google_client_id_list(self) -> list[str]:
        return [x.strip() for x in self.google_client_ids.split(",") if x.strip()]

    @property
    def bootstrap_admin_set(self) -> set[str]:
        return {x.strip().lower() for x in self.bootstrap_admin_emails.split(",") if x.strip()}


settings = Settings()
