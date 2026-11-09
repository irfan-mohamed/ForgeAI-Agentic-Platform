"""
Repository Knowledge Retriever.

Searches Qdrant for the most relevant code chunks given a user question.
Uses the same collection built by the Worker Service.

Payload contract with the Worker (see worker/app/services/vector_store.py):
    organization_id  int
    repository_id    int
    file_path        str
    chunk_index      int
    ... plus content, chunk_type, language, start_line, end_line

Tenant isolation: every query is filtered by organization_id AND
repository_id. Callers must pass IDs that came from
``app.core.access.get_repository``, never straight from a request body.
"""
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services import llm

logger = get_logger(__name__)

# Module-level singletons (initialized once on first call)
_qdrant_client: Any = None
_embed_model = None  # fastembed TextEmbedding singleton


def _qdrant():
    global _qdrant_client
    if _qdrant_client is None:
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError("qdrant-client is not installed. Run: pip install qdrant-client") from exc
        kwargs: dict = {"url": settings.QDRANT_URL}
        if settings.QDRANT_API_KEY:
            kwargs["api_key"] = settings.QDRANT_API_KEY
        _qdrant_client = QdrantClient(**kwargs)
    return _qdrant_client



@dataclass
class RetrievedChunk:
    """A single code/doc chunk returned from vector search."""
    chunk_id: str
    file_path: str
    chunk_type: str          # function / class / method / doc_section / raw
    content: str
    score: float             # Cosine similarity score (0–1)
    language: str
    start_line: int
    end_line: int
    chunk_index: int = 0


def _get_embed_model():
    """Returns the fastembed TextEmbedding model (loaded once per process)."""
    global _embed_model
    if _embed_model is None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "fastembed is not installed. Run: pip install fastembed"
            ) from exc
        logger.info(
            "Loading fastembed model for query embedding",
            extra={"model": settings.EMBEDDING_MODEL},
        )
        _embed_model = TextEmbedding(model_name=settings.EMBEDDING_MODEL)
    return _embed_model


def embed_query(query: str) -> list[float]:
    """Embed a user question using the same fastembed model as the Worker."""
    prefix = getattr(settings, "EMBEDDING_QUERY_PREFIX", "")
    prepared_query = f"{prefix}{query}" if prefix and not query.startswith(prefix) else query
    model = _get_embed_model()
    embeddings = list(model.embed([prepared_query]))
    return embeddings[0].tolist()


class _FallbackMatchValue:
    def __init__(self, value: Any):
        self.value = value


class _FallbackFieldCondition:
    def __init__(self, key: str, match: _FallbackMatchValue):
        self.key = key
        self.match = match


class _FallbackFilter:
    def __init__(self, must: list[_FallbackFieldCondition]):
        self.must = must


def tenant_filter(
    org_id: int,
    repository_id: int,
    file_path: str | None = None,
) -> Any:
    """
    Builds the mandatory tenant-isolation filter.

    Keys and types match the Worker's payload: ``organization_id`` and
    ``repository_id`` are stored as integers.
    """
    try:
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue
    except ImportError:
        FieldCondition = _FallbackFieldCondition
        Filter = _FallbackFilter
        MatchValue = _FallbackMatchValue

    must = [
        FieldCondition(key="organization_id", match=MatchValue(value=int(org_id))),
        FieldCondition(key="repository_id", match=MatchValue(value=int(repository_id))),
    ]
    if file_path:
        must.append(FieldCondition(key="file_path", match=MatchValue(value=file_path)))
    return Filter(must=must)




def _to_chunk(point_id, payload: dict | None, score: float) -> RetrievedChunk:
    p = payload or {}
    return RetrievedChunk(
        chunk_id=str(point_id),
        file_path=p.get("file_path", ""),
        chunk_type=p.get("chunk_type", "raw"),
        content=p.get("content", ""),
        score=score,
        language=p.get("language") or "",
        start_line=p.get("start_line", 0) or 0,
        end_line=p.get("end_line", 0) or 0,
        chunk_index=p.get("chunk_index", 0) or 0,
    )


def search_repository(
    query: str,
    org_id: int,
    repository_id: int,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """
    Semantic search over one repository's knowledge.

    Returns at most top_k chunks ordered by similarity score.
    """
    top_k = top_k or settings.RAG_TOP_K

    logger.info(
        "Searching repository knowledge",
        extra={"org_id": org_id, "repository_id": repository_id, "top_k": top_k},
    )

    query_vector = embed_query(query)

    hits = _qdrant().search(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=tenant_filter(org_id, repository_id),
        limit=top_k,
        with_payload=True,
    )

    chunks = [_to_chunk(hit.id, hit.payload, hit.score) for hit in hits]

    logger.info(
        "Search complete",
        extra={"chunks_returned": len(chunks), "top_score": chunks[0].score if chunks else 0},
    )
    return chunks


def fetch_file_chunks(
    org_id: int,
    repository_id: int,
    file_path: str,
    limit: int = 30,
) -> list[RetrievedChunk]:
    """
    Returns the stored chunks of one file, in file order (no embedding needed).

    Used by code review and test assistance to read exactly the file being
    discussed. The result is empty if the file was never indexed.
    """
    points, _next = _qdrant().scroll(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        scroll_filter=tenant_filter(org_id, repository_id, file_path),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    chunks = [_to_chunk(point.id, point.payload, 1.0) for point in points]
    chunks.sort(key=lambda c: (c.chunk_index, c.start_line))
    return chunks
