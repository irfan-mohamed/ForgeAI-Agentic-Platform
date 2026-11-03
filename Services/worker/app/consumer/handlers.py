"""
handlers.py — Top-level Kafka event handlers for the Worker Service.

Each function receives a raw Kafka message payload (dict) and orchestrates
the appropriate service calls. Handlers are async but the heavy work
(GitHub fetch, chunking, embedding) is delegated to services.

Idempotency:
  Every handler checks the current state before acting. If a sync is already
  RUNNING or COMPLETED, the event is silently skipped.

Error strategy:
  - On failure, update the RepositorySync/Repository status to FAILED.
  - Log the full exception with context.
  - Let the consumer commit the offset so the partition isn't blocked.
"""

import asyncio
import logging
from typing import Any

from app.db.database import get_db_session
from app.models.mirrors import Repository, RepositorySync, SyncStatus, RepositoryStatus
from app.services.sync_service import SyncService
from app.services.cleanup_service import CleanupService

logger = logging.getLogger(__name__)


async def handle_repository_connected(payload: dict[str, Any]) -> None:
    """
    Handles the ``repository.connected`` event.

    Published by the Repository Service when a user first connects a repo.
    The initial RepositorySync record with trigger=initial is already created.
    We just need to execute the sync job identified by sync_id.

    Payload fields:
        organization_id, repository_id, sync_id, trigger, timestamp
    """
    organization_id = payload.get("organization_id")
    repository_id = payload.get("repository_id")
    sync_id = payload.get("sync_id")

    logger.info(
        "Handling repository.connected",
        extra={"org_id": organization_id, "repo_id": repository_id, "sync_id": sync_id},
    )

    if not all([organization_id, repository_id, sync_id]):
        logger.error(
            "repository.connected payload missing required fields — skipping",
            extra={"payload": payload},
        )
        return

    await _run_sync_job(
        organization_id=organization_id,
        repository_id=repository_id,
        sync_id=sync_id,
    )


async def handle_sync_requested(payload: dict[str, Any]) -> None:
    """
    Handles the ``repository.sync.requested`` event.

    Published by the Repository Service for:
      - Manual re-sync requests (trigger=manual)
      - GitHub push webhooks (trigger=webhook_push)

    Payload fields:
        organization_id, repository_id, sync_id, trigger, timestamp
    """
    organization_id = payload.get("organization_id")
    repository_id = payload.get("repository_id")
    sync_id = payload.get("sync_id")

    logger.info(
        "Handling repository.sync.requested",
        extra={
            "org_id": organization_id,
            "repo_id": repository_id,
            "sync_id": sync_id,
            "trigger": payload.get("trigger"),
        },
    )

    if not all([organization_id, repository_id, sync_id]):
        logger.error(
            "repository.sync.requested payload missing required fields — skipping",
            extra={"payload": payload},
        )
        return

    await _run_sync_job(
        organization_id=organization_id,
        repository_id=repository_id,
        sync_id=sync_id,
    )


async def handle_repository_disconnected(payload: dict[str, Any]) -> None:
    """
    Handles the ``repository.disconnected`` event.

    Published when a user manually disconnects a repository from ForgeAI.
    We clean up all vectors and knowledge metadata for this repository.

    Payload fields:
        organization_id, repository_id, timestamp
    """
    organization_id = payload.get("organization_id")
    repository_id = payload.get("repository_id")

    logger.info(
        "Handling repository.disconnected — cleaning up knowledge",
        extra={"org_id": organization_id, "repo_id": repository_id},
    )

    if not all([organization_id, repository_id]):
        logger.error("repository.disconnected payload missing fields — skipping")
        return

    try:
        cleanup = CleanupService()
        await cleanup.cleanup_repository(
            organization_id=organization_id,
            repository_id=repository_id,
        )
    except Exception as exc:
        logger.exception(
            "Failed to clean up disconnected repository",
            extra={"repo_id": repository_id, "error": str(exc)},
        )


async def handle_access_revoked(payload: dict[str, Any]) -> None:
    """
    Handles the ``repository.access.revoked`` event.

    Published when the GitHub App is uninstalled or specific repos are
    removed from the installation. Same cleanup as disconnect.

    Payload fields:
        organization_id, repository_id, timestamp
    """
    organization_id = payload.get("organization_id")
    repository_id = payload.get("repository_id")

    logger.warning(
        "Handling repository.access.revoked — cleaning up knowledge",
        extra={"org_id": organization_id, "repo_id": repository_id},
    )

    if not all([organization_id, repository_id]):
        logger.error("repository.access.revoked payload missing fields — skipping")
        return

    try:
        cleanup = CleanupService()
        await cleanup.cleanup_repository(
            organization_id=organization_id,
            repository_id=repository_id,
        )
    except Exception as exc:
        logger.exception(
            "Failed to clean up access-revoked repository",
            extra={"repo_id": repository_id, "error": str(exc)},
        )


# ── Shared sync job runner ────────────────────────────────────────────────────

async def _run_sync_job(
    organization_id: int,
    repository_id: int,
    sync_id: int,
) -> None:
    """
    Core sync job runner shared by connected and sync-requested handlers.

    Idempotency check:
      If the sync record is already RUNNING or COMPLETED, we skip it.
      This handles Kafka at-least-once delivery (duplicate messages).

    The SyncService runs synchronously inside asyncio.to_thread() because
    Git operations and file I/O are blocking.
    """
    with get_db_session() as db:
        sync = db.get(RepositorySync, sync_id)
        if not sync:
            logger.error(
                "Sync record not found — cannot process",
                extra={"sync_id": sync_id, "repo_id": repository_id},
            )
            return

        if sync.status in (SyncStatus.RUNNING.value, SyncStatus.COMPLETED.value):
            logger.info(
                "Sync already running or completed — skipping duplicate event",
                extra={"sync_id": sync_id, "status": sync.status},
            )
            return

        repo = db.get(Repository, repository_id)
        if not repo:
            logger.error(
                "Repository record not found — cannot process sync",
                extra={"repo_id": repository_id},
            )
            return

    # Run the blocking sync in a thread pool so we don't block the event loop.
    sync_service = SyncService()
    await asyncio.to_thread(
        sync_service.run_sync,
        organization_id=organization_id,
        repository_id=repository_id,
        sync_id=sync_id,
    )
