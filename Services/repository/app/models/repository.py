import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RepositoryStatus(str, enum.Enum):
    """
    Lifecycle states of a connected repository.

    CONNECTING    — record created, waiting for first sync to start
    SYNCING       — Worker is downloading repository files from GitHub
    INDEXING      — Worker is chunking files and generating embeddings
    READY         — Repository knowledge is available for AI queries
    FAILED        — Sync or indexing failed (see latest RepositorySync for details)
    ACCESS_REVOKED — GitHub App was uninstalled or access was removed
    DISCONNECTED  — User manually disconnected the repository
    """

    CONNECTING = "connecting"
    SYNCING = "syncing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    ACCESS_REVOKED = "access_revoked"
    DISCONNECTED = "disconnected"


class Repository(Base):
    """
    A GitHub repository connected to a ForgeAI organization.

    Tenant isolation is enforced by always filtering on organization_id.
    A repository can only be connected once per organization (unique constraint).

    Data ownership: Repository Service.
    """

    __tablename__ = "repositories"

    __table_args__ = (
        # Prevent the same GitHub repo from being connected twice in one org.
        UniqueConstraint(
            "organization_id",
            "github_repository_id",
            name="uq_repo_org_github_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Tenant boundary — all queries must filter on this.
    organization_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # Which GitHub App installation granted access to this repo.
    github_installation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("github_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # GitHub's numeric repository ID (stored as string for safety with large IDs).
    github_repository_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # e.g. "backend"
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # e.g. "acme/backend"
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)

    # GitHub account login that owns the repo (e.g. "acme").
    owner: Mapped[str] = mapped_column(String(255), nullable=False)

    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # "public" | "private"
    visibility: Mapped[str] = mapped_column(String(20), nullable=False)

    # e.g. "main"
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)

    # Current lifecycle status.
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=RepositoryStatus.CONNECTING.value,
        server_default=RepositoryStatus.CONNECTING.value,
    )

    # Timestamp of the last successfully completed sync.
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    installation: Mapped["GitHubInstallation"] = relationship(  # type: ignore[name-defined]
        "GitHubInstallation",
        back_populates="repositories",
    )

    syncs: Mapped[list["RepositorySync"]] = relationship(  # type: ignore[name-defined]
        "RepositorySync",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="RepositorySync.created_at.desc()",
    )
