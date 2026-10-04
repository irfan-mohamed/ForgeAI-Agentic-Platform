import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MemberRole(str, enum.Enum):
    """
    Roles defined in PRD §23.

    COMPANY_ADMIN  — full platform control, manages users & integrations
    HR_ADMIN       — manages employees, templates, HR documents
    IT_ADMIN       — manages access requests and equipment workflows
    MANAGER        — views team onboarding, approves requests
    EMPLOYEE       — completes own onboarding tasks, asks AI questions
    """

    COMPANY_ADMIN = "company_admin"
    HR_ADMIN = "hr_admin"
    IT_ADMIN = "it_admin"
    MANAGER = "manager"
    EMPLOYEE = "employee"


# Convenience sets used by RBAC dependency
ADMIN_ROLES = {MemberRole.COMPANY_ADMIN, MemberRole.HR_ADMIN, MemberRole.IT_ADMIN}
MANAGEMENT_ROLES = {MemberRole.COMPANY_ADMIN, MemberRole.HR_ADMIN, MemberRole.MANAGER}
ALL_ROLES = set(MemberRole)


class Membership(Base):
    """
    Junction table: User ↔ Organization with a role.

    A user may belong to multiple organizations (e.g. a consultant).
    Within each organization they have exactly one role.
    """

    __tablename__ = "memberships"

    __table_args__ = (
        # A user can only have one membership per organization.
        UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Stored as the enum's string value, e.g. "company_admin"
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=MemberRole.EMPLOYEE.value,
    )

    # active | deactivated | pending_invite
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
        server_default="active",
    )

    joined_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    # Relationships ───────────────────────────────────────────────────
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User",
        back_populates="memberships",
    )

    organization: Mapped["Organization"] = relationship(  # type: ignore[name-defined]
        "Organization",
        back_populates="memberships",
    )
