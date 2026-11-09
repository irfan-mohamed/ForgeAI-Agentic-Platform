from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Service Identity ──────────────────────────────────────────────────────
    PROJECT_NAME: str = "ForgeAI AI Service"
    VERSION: str = "0.2.0"

    # ── Database (shared PostgreSQL) ──────────────────────────────────────────
    DATABASE_URL: str = "postgresql+psycopg://forgeai:Irfan%40123@localhost:5432/forgeai"

    # ── Auth (shared JWT secret with API service) ─────────────────────────────
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── Other services ────────────────────────────────────────────────────────
    REPOSITORY_SERVICE_URL: str = "http://localhost:8001"

    # ── Groq (chat + code review) ─────────────────────────────────────────────
    # Get a free key at: https://console.groq.com
    # The OpenAI SDK is used directly — Groq is 100% OpenAI-API-compatible.
    # base_url is set in llm.py: https://api.groq.com/openai/v1
    GROQ_API_KEY: str = ""
    # llama-3.3-70b-versatile: fast, accurate, 128k context, free tier
    GROQ_CHAT_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_REVIEW_MODEL: str = "llama-3.3-70b-versatile"

    # ── Embeddings (fastembed — local, no API key required) ───────────────────
    # Same model and dimensions as the Worker service — MUST match.
    # Model is downloaded from HuggingFace on first use and cached locally.
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSIONS: int = 384
    # BGE models are trained with an instruction prefix on the QUERY side only
    # (documents are embedded without it). Set to "" for models that don't use
    # one (e.g. jinaai/jina-embeddings-v2-base-code).
    EMBEDDING_QUERY_PREFIX: str = (
        "Represent this sentence for searching relevant passages: "
    )

    # ── Qdrant (vector search) ────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_NAME: str = "repository_knowledge"

    # ── RAG settings ──────────────────────────────────────────────────────────
    RAG_TOP_K: int = 8
    RAG_MAX_CONTEXT_TOKENS: int = 6000
    # Deterministic code-aware reranker applied after RRF fusion.
    RAG_RERANK_ENABLED: bool = True
    RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    RAG_CANDIDATE_POOL_SIZE: int = 30


    # ── Chat history limits ───────────────────────────────────────────────────
    CHAT_HISTORY_MAX_MESSAGES: int = 20
    CHAT_HISTORY_MAX_TOKENS: int = 6000

    # ── Code review limits ────────────────────────────────────────────────────
    REVIEW_MAX_DIFF_TOKENS: int = 24000
    REVIEW_MAX_FILE_PATCH_TOKENS: int = 4000
    REVIEW_MAX_CONTEXT_TOKENS: int = 8000
    REVIEW_MAX_FINDINGS: int = 30
    REVIEW_STALE_MINUTES: int = 30

    # ── Test assistance limits ────────────────────────────────────────────────
    TEST_MAX_CONTEXT_TOKENS: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
