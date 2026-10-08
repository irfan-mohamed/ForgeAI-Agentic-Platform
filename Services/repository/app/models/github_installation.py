import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InstallationStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class GitHubInstallation(Base):
    """
    Represents a GitHub App installation linked to a ForgeAI organization.

    When a user installs the ForgeAI GitHub App on their personal account
    or GitHub organization, GitHub issues a unique installation_id.
    This record connects that installation to a ForgeAI organization.

    One ForgeAI organization can have at most one active GitHub installation.
    One GitHub installation maps to exactly one ForgeAI organization.

    Data ownership: Repository Service (this service).
    The organization_id is stored as a plain int — no FK to users/organizations
    tables since those are owned by the api service. Relationship is enforced
    at the application level.
    """

    __tablename__ = "github_installations"

    __table_args__ = (
        # A GitHub installation can only be linked to one ForgeAI org.
        UniqueConstraint("github_installation_id", name="uq_github_installation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # ForgeAI organization that owns this installation.
    # Plain int — no FK to api service's organizations table.
    organization_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # The numeric installation ID that GitHub assigns.
    github_installation_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )

    # Numeric GitHub account/user/org ID.
    github_account_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # GitHub login name (e.g. "acme-corp" or "irfan-dev").
    github_account_login: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # "User" | "Organization"
    account_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # active | suspended | revoked
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=InstallationStatus.ACTIVE.value,
        server_default=InstallationStatus.ACTIVE.value,
    )

    installed_at: Mapped[datetime] = mapped_column(
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
    repositories: Mapped[list["Repository"]] = relationship(  # type: ignore[name-defined]
        "Repository",
        back_populates="installation",
        cascade="all, delete-orphan",
    )
