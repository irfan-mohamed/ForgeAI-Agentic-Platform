import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SyncStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SyncTrigger(str, enum.Enum):
    INITIAL = "initial"       # First sync after repository is connected
    MANUAL = "manual"         # User triggered via POST /repositories/{id}/sync
    WEBHOOK_PUSH = "webhook_push"  # GitHub push event received


class RepositorySync(Base):
    """
    Records one synchronization attempt for a repository.

    A repository may be synchronized many times throughout its lifecycle
    (initial sync, re-syncs from push events, manual re-syncs).
    Each attempt is tracked separately for full audit history.

    The Worker service updates status, progress counts, and error information
    as it processes the sync job.

    Data ownership: Repository Service.
    """

    __tablename__ = "repository_syncs"

    id: Mapped[int] = mapped_column(primary_key=True)

    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Current state of this sync attempt.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SyncStatus.QUEUED.value,
        server_default=SyncStatus.QUEUED.value,
    )

    # What caused this sync to be created.
    trigger: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=SyncTrigger.MANUAL.value,
    )

    # The HEAD commit SHA at the time of this sync (set by the Worker).
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Timestamps set by the Worker when processing starts/ends.
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Progress counters — updated by the Worker during processing.
    files_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Error detail if status = FAILED.
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    repository: Mapped["Repository"] = relationship(  # type: ignore[name-defined]
        "Repository",
        back_populates="syncs",
    )
