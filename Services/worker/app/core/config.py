import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Service Identity ──────────────────────────────────────────────────────
    PROJECT_NAME: str = "ForgeAI Worker Service"

    # ── Database ──────────────────────────────────────────────────────────────
    # Shared PostgreSQL with repository service.
    DATABASE_URL: str = (
        "postgresql+psycopg://forgeai:Irfan%40123@localhost:5432/forgeai"
    )

    # ── Kafka ─────────────────────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_CONSUMER_GROUP_ID: str = "forgeai-worker"
    KAFKA_TOPIC_REPOSITORY_EVENTS: str = "repository.events"
    KAFKA_TOPIC_REPOSITORY_SYNC: str = "repository.sync"
    KAFKA_MAX_POLL_RECORDS: int = 10

    # ── GitHub App ────────────────────────────────────────────────────────────
    GITHUB_APP_ID: str = ""
    GITHUB_APP_NAME: str = "forgeai-local"
    GITHUB_APP_PRIVATE_KEY: str = ""
    GITHUB_APP_PRIVATE_KEY_FILE: str = ""
    GITHUB_API_BASE_URL: str = "https://api.github.com"

    # ── Embeddings (fastembed — local, no API key required) ───────────────────
    # Model downloaded from HuggingFace on first use and cached locally.
    # BAAI/bge-small-en-v1.5 → 384 dimensions, fast, high quality.
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSIONS: int = 384

    # ── Qdrant (vector database) ──────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_NAME: str = "repository_knowledge"

    # ── Chunking ──────────────────────────────────────────────────────────────
    CHUNK_MAX_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 64

    # ── Local clone workspace ─────────────────────────────────────────────────
    CLONE_BASE_DIR: str = "/tmp/forgeai_worker_clones"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
