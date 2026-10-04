from datetime import datetime, timezone
from sqlalchemy import String, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Organization(Base):
    """
    Represents a tenant company in FlowForge.

    Every piece of data in the system (employees, documents, knowledge)
    belongs to an Organization.  Multi-tenancy is enforced by filtering
    all queries on organization_id.
    """

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # URL-safe identifier, e.g. "acme-corp".  Used in API paths and
    # can later become the subdomain slug.
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # active | suspended | inactive
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )

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

    # Relationships ───────────────────────────────────────────────────
    memberships: Mapped[list["Membership"]] = relationship(  # type: ignore[name-defined]
        "Membership",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
