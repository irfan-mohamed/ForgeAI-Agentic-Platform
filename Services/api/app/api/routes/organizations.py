from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_org_membership,
    require_roles,
)
from app.db.database import get_db
from app.models.membership import MemberRole
from app.models.user import User
from app.schemas.membership import MembershipResponse, MembershipWithUserResponse, MemberRoleUpdate, MemberCreate
from app.schemas.organization import OrganizationCreate, OrganizationResponse
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization",
)
def create_organization(
    org_in: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """
    Creates a new organization (tenant) and automatically grants
    the requesting user COMPANY_ADMIN role.

    Any authenticated user can create an organization.
    """
    return OrganizationService.create_organization(
        org_in=org_in,
        creator_user_id=current_user.id,
        db=db,
    )


@router.get(
    "",
    response_model=list[OrganizationResponse],
    summary="List my organizations",
)
def list_organizations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrganizationResponse]:
    """Returns all active organizations the current user belongs to."""
    return OrganizationService.list_user_organizations(
        user_id=current_user.id,
        db=db,
    )


@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Get organization details",
)
def get_organization(
    org_id: int,
    db: Session = Depends(get_db),
    # Membership check — raises 403 if the caller is not a member
    _membership=Depends(get_org_membership),
) -> OrganizationResponse:
    """Returns the organization details. Only visible to members."""
    return OrganizationService.get_organization(org_id=org_id, db=db)


@router.get(
    "/{org_id}/members",
    response_model=list[MembershipWithUserResponse],
    summary="List organization members",
)
def list_members(
    org_id: int,
    db: Session = Depends(get_db),
    _membership=Depends(get_org_membership),
) -> list[MembershipWithUserResponse]:
    """Returns all active members of the organization. Any member can view."""
    return OrganizationService.list_members(org_id=org_id, db=db)

@router.post(
    "/{org_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    org_id: int,
    member_in: MemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _membership=Depends(require_roles(MemberRole.COMPANY_ADMIN)),
):
    return OrganizationService.add_member_by_email(
        org_id=org_id,
        email=member_in.email,
        role=MemberRole.EMPLOYEE,
        db=db,
        added_by=current_user.id,
    )


@router.patch(
    "/{org_id}/members/{user_id}/role",
    response_model=MembershipResponse,
    summary="Update a member's role",
)
def update_member_role(
    org_id: int,
    user_id: int,
    role_in: MemberRoleUpdate,
    db: Session = Depends(get_db),
    # Only COMPANY_ADMIN can change roles
    _membership=Depends(require_roles(MemberRole.COMPANY_ADMIN)),
) -> MembershipResponse:
    """Updates the role of a member within the organization."""
    return OrganizationService.update_member_role(
        org_id=org_id,
        user_id=user_id,
        new_role=role_in.role,
        db=db,
    )
