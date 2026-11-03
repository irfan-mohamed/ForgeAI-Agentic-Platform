"""
embedder.py — Local embedding generation for the Worker Service using fastembed.

Uses fastembed (maintained by the Qdrant team) to generate dense embeddings
locally — no API key, no cost, no rate limits.

The model is downloaded from HuggingFace on first use and cached on disk.

Design decisions:
  - Uses BAAI/bge-small-en-v1.5 by default (384 dimensions, fast, high quality).
  - Batches up to 256 chunks per forward pass for efficiency.
  - A single module-level TextEmbedding instance is reused across calls (warm).
  - Records the model name in each RepositoryKnowledge record so we can
    detect stale embeddings if we change models in the future.
  - Pre-cleans text: strips null bytes and control characters.
"""

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded singleton — fastembed loads the ONNX model on first call.
_embedding_model = None

# Max chunks per fastembed batch call (CPU-friendly)
BATCH_SIZE = 256


def _get_model():
    """Returns the fastembed TextEmbedding model (loaded once per process)."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "fastembed is not installed. Run: pip install fastembed"
            ) from exc

        logger.info(
            "Loading fastembed embedding model",
            extra={"model": settings.EMBEDDING_MODEL},
        )
        _embedding_model = TextEmbedding(
            model_name=settings.EMBEDDING_MODEL,
            max_length=settings.CHUNK_MAX_TOKENS,
        )
        logger.info("Fastembed model loaded and ready")
    return _embedding_model


def _clean_text(text: str) -> str:
    """
    Sanitizes text before embedding.
    Removes null bytes and control characters that can cause issues.
    """
    text = text.replace("\x00", "")
    text = "".join(
        ch for ch in text
        if ch in ("\n", "\t", "\r") or (ord(ch) >= 32 and ord(ch) < 127) or ord(ch) > 127
    )
    return text.strip()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generates embeddings for a list of text strings using a local fastembed model.

    Processes all texts in a single batched forward pass (fastembed handles
    internal batching automatically).

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (list of floats), in the same order as input.

    Raises:
        RuntimeError if the model fails to load or embed.
    """
    if not texts:
        return []

    model = _get_model()

    # Clean texts
    cleaned = [_clean_text(t) for t in texts]
    # Replace empty strings with a single space (models need non-empty input)
    cleaned = [t if t else " " for t in cleaned]

    try:
        # fastembed.embed() returns a generator of numpy arrays
        embeddings_gen = model.embed(cleaned, batch_size=BATCH_SIZE)
        result = [emb.tolist() for emb in embeddings_gen]
        logger.debug("Embeddings generated", extra={"count": len(result)})
        return result

    except Exception as exc:
        raise RuntimeError(f"fastembed embedding failed: {exc}") from exc


def get_model_name() -> str:
    """Returns the embedding model name from settings (recorded in DB)."""
    return settings.EMBEDDING_MODEL


def get_embedding_dimensions() -> int:
    """Returns the number of dimensions for the current embedding model."""
    return settings.EMBEDDING_DIMENSIONS
