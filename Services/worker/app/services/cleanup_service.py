"""
cleanup_service.py — Removes all knowledge data for a repository.

Called when:
  - A repository is disconnected by the user (repository.disconnected event)
  - GitHub App access is revoked (repository.access.revoked event)

Cleanup steps:
  1. Delete all vectors from Qdrant for this repository_id
  2. Delete all RepositoryKnowledge metadata records from PostgreSQL
  3. Delete all RepositoryFile records from PostgreSQL

We do NOT delete the Repository or RepositorySync records —
those are owned by the Repository Service.
"""

import logging

from app.db.database import get_db_session
from app.models.repository_file import RepositoryFile
from app.models.repository_knowledge import RepositoryKnowledge
from app.services import vector_store

logger = logging.getLogger(__name__)


class CleanupService:
    """Handles all cleanup operations when a repository is removed from ForgeAI."""

    async def cleanup_repository(
        self,
        organization_id: int,
        repository_id: int,
    ) -> None:
        """
        Removes all knowledge data for a repository from Qdrant and PostgreSQL.

        Runs in this order to ensure partial failures don't leave orphaned data:
          1. Qdrant vectors first (can be safely retried — idempotent delete)
          2. PostgreSQL knowledge metadata
          3. PostgreSQL file metadata

        If Qdrant deletion fails, we still attempt the PostgreSQL cleanup
        since stale metadata is worse than orphaned vectors (vectors are
        safe to leave; metadata causes incorrect state tracking).
        """
        logger.info(
            "Starting repository cleanup",
            extra={"org_id": organization_id, "repo_id": repository_id},
        )

        # ── Step 1: Delete Qdrant vectors ─────────────────────────────────────
        try:
            vector_store.delete_vectors_by_repository(repository_id)
            logger.info(
                "Qdrant vectors deleted",
                extra={"repo_id": repository_id},
            )
        except Exception as exc:
            logger.error(
                "Failed to delete Qdrant vectors — continuing with DB cleanup",
                extra={"repo_id": repository_id, "error": str(exc)},
            )

        # ── Step 2: Delete PostgreSQL knowledge metadata ───────────────────────
        try:
            with get_db_session() as db:
                deleted_knowledge = (
                    db.query(RepositoryKnowledge)
                    .filter(RepositoryKnowledge.repository_id == repository_id)
                    .delete()
                )
                db.commit()
            logger.info(
                "Knowledge metadata deleted",
                extra={"repo_id": repository_id, "count": deleted_knowledge},
            )
        except Exception as exc:
            logger.error(
                "Failed to delete knowledge metadata",
                extra={"repo_id": repository_id, "error": str(exc)},
            )

        # ── Step 3: Delete PostgreSQL file metadata ────────────────────────────
        try:
            with get_db_session() as db:
                deleted_files = (
                    db.query(RepositoryFile)
                    .filter(RepositoryFile.repository_id == repository_id)
                    .delete()
                )
                db.commit()
            logger.info(
                "File metadata deleted",
                extra={"repo_id": repository_id, "count": deleted_files},
            )
        except Exception as exc:
            logger.error(
                "Failed to delete file metadata",
                extra={"repo_id": repository_id, "error": str(exc)},
            )

        logger.info(
            "Repository cleanup completed",
            extra={"org_id": organization_id, "repo_id": repository_id},
        )
