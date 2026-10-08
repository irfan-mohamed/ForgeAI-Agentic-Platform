"""
kafka_producer.py — Event publishing for the Repository Service.

Phase 1 (current): STUB MODE
    When KAFKA_ENABLED=false (default), events are only logged at INFO level.
    This allows full development and testing of the Repository Service without
    a running Kafka cluster.

Phase 2 (when Worker is built): REAL MODE
    Set KAFKA_ENABLED=true in .env.
    The producer will publish JSON messages to the configured Kafka topics.

Event envelope structure (same format the Worker will consume):
    {
        "event": "repository.sync.requested",
        "organization_id": 1,
        "repository_id": 42,
        "sync_id": 7,
        "trigger": "initial",
        "timestamp": "2026-10-07T09:30:00Z"
    }
"""

import json
import logging
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(topic: str, payload: dict) -> None:
    """
    Core publish function.
    In stub mode: logs the event.
    In real mode: publishes to Kafka (requires running broker).
    """
    if not settings.KAFKA_ENABLED:
        logger.info(
            "kafka event (stub — not published)",
            extra={
                "kafka_topic": topic,
                "kafka_event": payload.get("event"),
                "organization_id": payload.get("organization_id"),
                "repository_id": payload.get("repository_id"),
            },
        )
        return

    # ── Real Kafka publish ────────────────────────────────────────────────────
    # Uncomment and complete when Worker service is ready.
    # from aiokafka import AIOKafkaProducer
    # ...
    # This will be implemented in Phase 2 (Worker service sprint).
    logger.warning(
        "KAFKA_ENABLED=true but real producer is not yet implemented. "
        "Event dropped.",
        extra={"kafka_topic": topic, "payload": payload},
    )


# ── Public API ────────────────────────────────────────────────────────────────

def publish_repository_connected(
    organization_id: int,
    repository_id: int,
    sync_id: int,
) -> None:
    """
    Published when a repository is first connected to ForgeAI.
    The Worker responds by starting the initial repository sync.
    """
    _emit(
        topic=settings.KAFKA_TOPIC_REPOSITORY_EVENTS,
        payload={
            "event": "repository.connected",
            "organization_id": organization_id,
            "repository_id": repository_id,
            "sync_id": sync_id,
            "trigger": "initial",
            "timestamp": _now_iso(),
        },
    )


def publish_sync_requested(
    organization_id: int,
    repository_id: int,
    sync_id: int,
    trigger: str,
) -> None:
    """
    Published when a sync is requested (manual or webhook-triggered).
    The Worker picks this up and begins file processing.
    """
    _emit(
        topic=settings.KAFKA_TOPIC_REPOSITORY_SYNC,
        payload={
            "event": "repository.sync.requested",
            "organization_id": organization_id,
            "repository_id": repository_id,
            "sync_id": sync_id,
            "trigger": trigger,
            "timestamp": _now_iso(),
        },
    )


def publish_repository_disconnected(
    organization_id: int,
    repository_id: int,
) -> None:
    """
    Published when a user disconnects a repository.
    The Worker (and AI service) can use this to clean up related data.
    """
    _emit(
        topic=settings.KAFKA_TOPIC_REPOSITORY_EVENTS,
        payload={
            "event": "repository.disconnected",
            "organization_id": organization_id,
            "repository_id": repository_id,
            "timestamp": _now_iso(),
        },
    )


def publish_access_revoked(
    organization_id: int,
    repository_id: int,
) -> None:
    """
    Published when GitHub revokes access (App uninstalled).
    Consumers should stop any active processing for this repository.
    """
    _emit(
        topic=settings.KAFKA_TOPIC_REPOSITORY_EVENTS,
        payload={
            "event": "repository.access.revoked",
            "organization_id": organization_id,
            "repository_id": repository_id,
            "timestamp": _now_iso(),
        },
    )
