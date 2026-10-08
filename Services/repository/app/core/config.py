import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    # Shared PostgreSQL instance with the api service.
    DATABASE_URL: str = (
        "postgresql+psycopg://forgeai:Irfan%40123@localhost:5432/forgeai"
    )

    # ── Service Identity ──────────────────────────────────────────────────────
    PROJECT_NAME: str = "ForgeAI Repository Service"
    API_V1_STR: str = "/api/v1"

    # ── JWT ───────────────────────────────────────────────────────────────────
    # Must match the SECRET_KEY and ALGORITHM in the api service so that tokens
    # issued by api/auth can be verified here without an inter-service call.
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALGORITHM: str = "HS256"

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── GitHub App ────────────────────────────────────────────────────────────
    GITHUB_APP_ID: str = ""
    GITHUB_APP_NAME: str = "forgeai-dev"
    # Full PEM private key (multiline). In .env use escaped newlines or a file path.
    GITHUB_APP_PRIVATE_KEY: str = ""
    # Secret used to validate X-Hub-Signature-256 on incoming webhooks.
    GITHUB_WEBHOOK_SECRET: str = ""
    # Where to redirect the user after the GitHub callback completes.
    GITHUB_CALLBACK_REDIRECT_URL: str = "http://localhost:5173/github/callback"
    # GitHub API base URL (can be overridden for GitHub Enterprise).
    GITHUB_API_BASE_URL: str = "https://api.github.com"

    # ── Kafka ─────────────────────────────────────────────────────────────────
    # Set to False initially — Kafka events are only logged until Worker is ready.
    KAFKA_ENABLED: bool = False
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_REPOSITORY_EVENTS: str = "repository.events"
    KAFKA_TOPIC_REPOSITORY_SYNC: str = "repository.sync"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
