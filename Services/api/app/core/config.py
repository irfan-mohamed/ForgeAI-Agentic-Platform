import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ───────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+psycopg://forgeai:Irfan%40123@localhost:5432/forgeai"
    )

    # ── API ────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "FlowForge API"
    API_V1_STR: str = "/api/v1"

    # ── Auth / JWT ─────────────────────────────────────────────────────
    # Override SECRET_KEY via .env in all environments.
    # Never commit real secrets to version control.
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRY_MINUTES: int = 60   # 1 hour; tune per environment
    REFRESH_TOKEN_EXPIRY_DAYS: int = 7

    # ── CORS ───────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins for the frontend
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8001"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()