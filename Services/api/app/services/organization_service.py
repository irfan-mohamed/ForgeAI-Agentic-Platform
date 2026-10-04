import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.organization import Organization
from app.models.membership import Membership, MemberRole
from app.models.user import User
from app.schemas.organization import OrganizationCreate

logger = logging.getLogger(__name__)


class OrganizationService:
    """
    Deterministic service for Organization and Membership operations.

    Agents must never call the database directly — they go through this
    service so that business rules are applied consistently (PRD §10).
    """

    # ── Organization CRUD ─────────────────────────────────────────────

    @staticmethod
    def create_organization(
        org_in: OrganizationCreate,
        creator_user_id: int,
        db: Session,
    ) -> Organization:
        """
        Creates a new organization and makes the creator a COMPANY_ADMIN.

        Raises 409 if the slug is already taken.
        """
        existing = (
            db.query(Organization)
            .filter(Organization.slug == org_in.slug)
            .first()
        )
        if existing:
            logger.warning(
                "Organization creation failed — slug already exists",
                extra={"slug": org_in.slug, "user_id": creator_user_id},
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An organization with slug '{org_in.slug}' already exists.",
            )

        org = Organization(
            name=org_in.name,
            slug=org_in.slug,
            description=org_in.description,
            status="active",
        )
        db.add(org)
        db.flush()  # populate org.id before creating the membership

        # The creator automatically becomes COMPANY_ADMIN
        membership = Membership(
            user_id=creator_user_id,
            organization_id=org.id,
            role=MemberRole.COMPANY_ADMIN.value,
            status="active",
        )
        db.add(membership)
        db.commit()
        db.refresh(org)

        logger.info(
            "Organization created",
            extra={"org_id": org.id, "slug": org.slug, "created_by": creator_user_id},
        )
        return org

    @staticmethod
    def get_organization(org_id: int, db: Session) -> Organization:
        """Returns an organization by ID or raises 404."""
        org = db.get(Organization, org_id)
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found.",
            )
        return org

    @staticmethod
    def get_by_slug(slug: str, db: Session) -> Organization:
        """Returns an organization by slug or raises 404."""
        org = db.query(Organization).filter(Organization.slug == slug).first()
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found.",
            )
        return org

    @staticmethod
    def list_user_organizations(user_id: int, db: Session) -> list[Organization]:
        """Returns all active organizations the user is a member of."""
        return (
            db.query(Organization)
            .join(Membership, Membership.organization_id == Organization.id)
            .filter(
                Membership.user_id == user_id,
                Membership.status == "active",
                Organization.status == "active",
            )
            .order_by(Organization.name)
            .all()
        )

    # ── Membership ────────────────────────────────────────────────────

    @staticmethod
    def get_membership(
        user_id: int, org_id: int, db: Session
    ) -> Membership | None:
        """Returns the membership record or None."""
        return (
            db.query(Membership)
            .filter(
                Membership.user_id == user_id,
                Membership.organization_id == org_id,
            )
            .first()
        )

    @staticmethod
    def list_members(org_id: int, db: Session) -> list[Membership]:
        """Returns all active memberships for an organization."""
        return (
            db.query(Membership)
            .filter(
                Membership.organization_id == org_id,
                Membership.status == "active",
            )
            .all()
        )

    @staticmethod
    def add_member(
        org_id: int,
        user_id: int,
        role: MemberRole,
        db: Session,
        added_by: int | None = None,
    ) -> Membership:
        """
        Adds a user to an organization with a given role.

        Raises 409 if the user is already a member.
        """
        existing = OrganizationService.get_membership(user_id, org_id, db)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this organization.",
            )

        membership = Membership(
            user_id=user_id,
            organization_id=org_id,
            role=role.value,
            status="active",
        )
        db.add(membership)
        db.commit()
        db.refresh(membership)

        logger.info(
            "Member added to organization",
            extra={
                "org_id": org_id,
                "user_id": user_id,
                "role": role.value,
                "added_by": added_by,
            },
        )
        return membership

    @staticmethod
    def add_member_by_email(
            org_id: int,
            email: str,
            role: MemberRole,
            db: Session,
            added_by: int | None = None,
        ) -> Membership:

            user = (
                db.query(User)
                .filter(User.email == email)
                .first()
            )

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

            return OrganizationService.add_member(
                org_id=org_id,
                user_id=user.id,
                role=role,
                db=db,
                added_by=added_by,
            )


    @staticmethod
    def update_member_role(
        org_id: int,
        user_id: int,
        new_role: MemberRole,
        db: Session,
    ) -> Membership:
        """Changes the role of an existing member. Raises 404 if not found."""
        membership = OrganizationService.get_membership(user_id, org_id, db)
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Membership not found.",
            )
        membership.role = new_role.value
        db.commit()
        db.refresh(membership)

        logger.info(
            "Member role updated",
            extra={"org_id": org_id, "user_id": user_id, "new_role": new_role.value},
        )
        return membership
