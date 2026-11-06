"""
vector_store.py — Qdrant vector database client for the Worker Service.

Responsibilities:
  - Ensure the repository_knowledge collection exists at startup
  - Upsert vectors with rich metadata (org_id, repo_id, file_path, etc.)
  - Delete vectors by repository_id (for cleanup on disconnect/revoke)
  - Delete vectors by file (for incremental re-sync of changed files)
  - Search vectors by organization/repository (used by AI Service)

Collection design:
  One collection ("repository_knowledge") stores ALL chunks from ALL orgs/repos.
  Tenant isolation is enforced via metadata payload filters:
    - organization_id (int)  — primary tenant boundary
    - repository_id   (int)  — secondary boundary
    - file_path       (str)  — for file-level operations
    - chunk_type      (str)  — "function", "class", "method", etc.
    - language        (str)  — "python", "typescript", etc.

  This design allows the AI Service to filter by org+repo and also
  narrow searches by file type, language, or chunk kind.

Vector IDs:
  Each chunk is assigned a UUID stored in both Qdrant and the
  repository_knowledge PostgreSQL table (as vector_id).
  This creates a bidirectional reference for cleanup operations.
"""

import logging
import uuid
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_client():
    """Returns a Qdrant client, lazy-imported to avoid startup errors if not configured."""
    from qdrant_client import QdrantClient
    from qdrant_client.http.exceptions import UnexpectedResponse

    kwargs: dict[str, Any] = {"url": settings.QDRANT_URL}
    if settings.QDRANT_API_KEY:
        kwargs["api_key"] = settings.QDRANT_API_KEY

    return QdrantClient(**kwargs)


def _get_collection_vector_dimension(col_info: Any) -> int | None:
    """Extract vector dimension/size from Qdrant CollectionInfo."""
    try:
        config = getattr(col_info, "config", None)
        params = getattr(config, "params", None)
        vectors = getattr(params, "vectors", None)
        if vectors is None:
            return None
        if hasattr(vectors, "size") and isinstance(vectors.size, int):
            return vectors.size
        if isinstance(vectors, dict):
            for v in vectors.values():
                if hasattr(v, "size") and isinstance(v.size, int):
                    return v.size
                if isinstance(v, dict) and "size" in v and isinstance(v["size"], int):
                    return v["size"]
    except Exception as exc:
        logger.warning("Could not extract vector dimension from CollectionInfo: %s", exc)
    return None


def _reset_db_knowledge_and_files() -> None:
    """
    Clears repository_knowledge and marks repository_files for re-indexing
    when the Qdrant collection is recreated due to dimension mismatch.
    """
    try:
        from app.db.database import get_db_session
        from sqlalchemy import text

        with get_db_session() as db:
            db.execute(text("DELETE FROM repository_knowledge"))
            db.execute(
                text(
                    "UPDATE repository_files "
                    "SET is_indexed = false, status = 'discovered', last_error = NULL "
                    "WHERE is_indexed = true OR status = 'failed'"
                )
            )
            db.commit()
        logger.info("Reset repository_files and cleared repository_knowledge due to collection recreation")
    except Exception as exc:
        logger.warning("Could not reset DB tables after collection recreation: %s", exc)


def ensure_collection_exists() -> None:
    """
    Creates the Qdrant collection if it doesn't already exist or if dimensions mismatch.

    Called once at worker startup and at the start of each sync job. Idempotent.

    Collection configuration:
      - Vector size: matches EMBEDDING_DIMENSIONS (default 384 for BAAI/bge-small-en-v1.5)
      - Distance: Cosine similarity (standard for semantic search)
      - Payload indexing: on key fields for fast filtered search
    """
    from qdrant_client.models import (
        Distance, VectorParams,
        PayloadSchemaType,
    )

    client = _get_client()
    collection_name = settings.QDRANT_COLLECTION_NAME

    try:
        col_info = client.get_collection(collection_name)
        current_dim = _get_collection_vector_dimension(col_info)
        if current_dim == settings.EMBEDDING_DIMENSIONS:
            logger.info(
                "Qdrant collection already exists with matching dimensions",
                extra={"collection": collection_name, "dimensions": current_dim},
            )
            return

        logger.warning(
            "Qdrant collection dimension mismatch (existing: %s, expected: %s). Recreating collection.",
            current_dim,
            settings.EMBEDDING_DIMENSIONS,
            extra={
                "collection": collection_name,
                "existing_dim": current_dim,
                "expected_dim": settings.EMBEDDING_DIMENSIONS,
            },
        )
        try:
            client.delete_collection(collection_name)
        except Exception as exc:
            logger.warning("Error deleting outdated collection: %s", exc)

        _reset_db_knowledge_and_files()
    except Exception as exc:
        # Collection does not exist yet or connection error to be handled by create
        logger.debug("Collection check or fetch exception: %s", exc)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=settings.EMBEDDING_DIMENSIONS,
            distance=Distance.COSINE,
        ),
    )

    # Create payload indexes for fast filtered search.
    # These are the fields the AI Service will filter on.
    for field_name, field_type in [
        ("organization_id", PayloadSchemaType.INTEGER),
        ("repository_id", PayloadSchemaType.INTEGER),
        ("file_path", PayloadSchemaType.KEYWORD),
        ("language", PayloadSchemaType.KEYWORD),
        ("chunk_type", PayloadSchemaType.KEYWORD),
    ]:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=field_type,
        )

    logger.info(
        "Qdrant collection created",
        extra={
            "collection": collection_name,
            "dimensions": settings.EMBEDDING_DIMENSIONS,
        },
    )


def upsert_vectors(points: list[dict[str, Any]]) -> None:
    """
    Upserts a batch of vectors into the Qdrant collection.

    Each point must have:
        {
            "id": str (UUID),
            "vector": list[float],
            "payload": {
                "organization_id": int,
                "repository_id": int,
                "repository_file_id": int,
                "file_path": str,
                "commit_sha": str | None,
                "language": str | None,
                "chunk_type": str,
                "chunk_name": str | None,
                "chunk_index": int,
                "start_line": int,
                "end_line": int,
                "content": str,           # Stored for retrieval/citation
                "token_count": int,
                "embedding_model": str,
            }
        }

    Raises RuntimeError on Qdrant failure.
    """
    if not points:
        return

    from qdrant_client.models import PointStruct

    client = _get_client()
    qdrant_points = [
        PointStruct(
            id=p["id"],
            vector=p["vector"],
            payload=p["payload"],
        )
        for p in points
    ]

    try:
        client.upsert(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points=qdrant_points,
        )
    except Exception as exc:
        err_msg = str(exc)
        if "expected dim" in err_msg or "Wrong input: Vector inserting error" in err_msg:
            logger.warning(
                "Dimension mismatch during vector upsert (%s). Recreating collection and retrying.",
                err_msg,
            )
            ensure_collection_exists()
            client.upsert(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                points=qdrant_points,
            )
        else:
            raise

    logger.debug(
        "Qdrant vectors upserted",
        extra={"count": len(points)},
    )


def delete_vectors_by_repository(repository_id: int) -> int:
    """
    Deletes ALL vectors belonging to a repository.

    Used when:
      - A repository is disconnected (user action)
      - GitHub App access is revoked

    Returns the number of vectors deleted (approximate — Qdrant doesn't
    always provide exact counts, so we return the filter match count).
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = _get_client()

    result = client.delete(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="repository_id",
                    match=MatchValue(value=repository_id),
                )
            ]
        ),
    )

    logger.info(
        "Qdrant vectors deleted for repository",
        extra={"repository_id": repository_id},
    )
    return 0  # Qdrant delete doesn't return count directly


def delete_vectors_by_file(repository_id: int, file_path: str) -> None:
    """
    Deletes all vectors for a specific file within a repository.

    Used during incremental re-sync when a file has changed:
      1. Delete old vectors for this file
      2. Re-chunk and re-embed the new content
      3. Insert new vectors

    This ensures the knowledge base is always up-to-date.
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = _get_client()

    client.delete(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="repository_id",
                    match=MatchValue(value=repository_id),
                ),
                FieldCondition(
                    key="file_path",
                    match=MatchValue(value=file_path),
                ),
            ]
        ),
    )

    logger.debug(
        "Qdrant vectors deleted for file",
        extra={"repository_id": repository_id, "file_path": file_path},
    )


def delete_vectors_by_ids(vector_ids: list[str]) -> None:
    """
    Deletes specific vectors by their UUID.

    Used when we have the exact vector_ids from the repository_knowledge table.
    More precise than filter-based deletion.
    """
    if not vector_ids:
        return

    client = _get_client()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points_selector=vector_ids,
    )


def generate_vector_id() -> str:
    """Generates a new UUID string for a vector point."""
    return str(uuid.uuid4())


def search_vectors(
    query_vector: list[float],
    organization_id: int,
    repository_id: int | None = None,
    language: str | None = None,
    chunk_type: str | None = None,
    top_k: int = 10,
    score_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """
    Searches for similar vectors within an organization's knowledge base.

    This is called by the AI Service (not the Worker), but lives here
    to keep all Qdrant logic centralized.

    Applies mandatory organization_id filter for tenant isolation.
    Optionally filters by repository, language, and chunk type.

    Returns a list of results with score and payload:
        [{
            "id": str,
            "score": float,
            "payload": { file_path, content, chunk_name, chunk_type, ... }
        }]
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    must_conditions = [
        FieldCondition(
            key="organization_id",
            match=MatchValue(value=organization_id),
        )
    ]

    if repository_id is not None:
        must_conditions.append(
            FieldCondition(
                key="repository_id",
                match=MatchValue(value=repository_id),
            )
        )

    if language:
        must_conditions.append(
            FieldCondition(
                key="language",
                match=MatchValue(value=language),
            )
        )

    if chunk_type:
        must_conditions.append(
            FieldCondition(
                key="chunk_type",
                match=MatchValue(value=chunk_type),
            )
        )

    client = _get_client()
    results = client.search(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=Filter(must=must_conditions),
        limit=top_k,
        score_threshold=score_threshold,
        with_payload=True,
    )

    return [
        {
            "id": str(r.id),
            "score": r.score,
            "payload": r.payload,
        }
        for r in results
    ]
