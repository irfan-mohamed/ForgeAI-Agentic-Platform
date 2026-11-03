"""
kafka_consumer.py — Kafka event consumer for the Worker Service.

Subscribes to:
  - repository.events  (connected, disconnected, access.revoked)
  - repository.sync    (sync.requested)

Each message is dispatched to the appropriate handler by event type.

Design decisions:
  - aiokafka is used for native async consumption.
  - One consumer group ("forgeai-worker") — Kafka handles partition assignment.
  - Messages are committed AFTER successful processing (at-least-once delivery).
  - If processing fails, the error is logged and the message is still committed
    so it doesn't block the partition. Failures are recorded in the DB.
  - Idempotency is enforced inside each handler (check sync status before acting).
"""

import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

from app.core.config import settings
from app.core.logging import event_var, job_id_var

logger = logging.getLogger(__name__)


class WorkerConsumer:
    """
    Manages the Kafka consumer lifecycle and message dispatch.
    """

    def __init__(self) -> None:
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False

    async def start(self) -> None:
        """Initialize and start the Kafka consumer."""
        self._consumer = AIOKafkaConsumer(
            settings.KAFKA_TOPIC_REPOSITORY_EVENTS,
            settings.KAFKA_TOPIC_REPOSITORY_SYNC,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=settings.KAFKA_CONSUMER_GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=False,       # Manual commit — commit after success
            max_poll_records=settings.KAFKA_MAX_POLL_RECORDS,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        await self._consumer.start()
        self._running = True
        logger.info(
            "Kafka consumer started",
            extra={
                "topics": [
                    settings.KAFKA_TOPIC_REPOSITORY_EVENTS,
                    settings.KAFKA_TOPIC_REPOSITORY_SYNC,
                ],
                "group_id": settings.KAFKA_CONSUMER_GROUP_ID,
            },
        )

    async def stop(self) -> None:
        """Gracefully stop the consumer."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        logger.info("Kafka consumer stopped")

    async def run(self) -> None:
        """
        Main consumption loop.

        Reads messages one by one and dispatches them to handlers.
        Commits offset after each message regardless of success/failure
        to avoid blocking partitions. Errors are recorded in the database.
        """
        if not self._consumer:
            raise RuntimeError("Consumer not started — call start() first.")

        async for message in self._consumer:
            if not self._running:
                break

            payload: dict[str, Any] = message.value
            event_type = payload.get("event", "unknown")

            # Set context vars so all log lines during this message are tagged.
            event_token = event_var.set(event_type)
            job_token = job_id_var.set(str(payload.get("sync_id", "-")))

            logger.info(
                "Kafka message received",
                extra={
                    "topic": message.topic,
                    "partition": message.partition,
                    "offset": message.offset,
                    "event": event_type,
                    "organization_id": payload.get("organization_id"),
                    "repository_id": payload.get("repository_id"),
                },
            )

            try:
                await self._dispatch(event_type, payload)
            except Exception as exc:
                logger.exception(
                    "Unhandled error processing Kafka message — skipping",
                    extra={"event": event_type, "error": str(exc)},
                )
            finally:
                # Always commit so we don't re-process on restart.
                await self._consumer.commit()
                event_var.reset(event_token)
                job_id_var.reset(job_token)

    async def _dispatch(self, event_type: str, payload: dict[str, Any]) -> None:
        """
        Route message to the correct handler based on event type.

        Import handlers lazily to keep startup fast and avoid circular imports.
        """
        # Import here to avoid top-level circular dependencies.
        from app.consumer import handlers

        if event_type == "repository.connected":
            await handlers.handle_repository_connected(payload)

        elif event_type == "repository.sync.requested":
            await handlers.handle_sync_requested(payload)

        elif event_type == "repository.disconnected":
            await handlers.handle_repository_disconnected(payload)

        elif event_type == "repository.access.revoked":
            await handlers.handle_access_revoked(payload)

        else:
            logger.info(
                "Unrecognised event type — acknowledged and ignored",
                extra={"event": event_type},
            )
