from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.membership import MemberRole
from app.schemas.user import UserResponse

class MemberCreate(BaseModel):
    """Add members to the organizations."""

    email : EmailStr
    role : MemberRole = MemberRole.EMPLOYEE

class MembershipResponse(BaseModel):
    """Membership record including the member's public user info."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    organization_id: int
    role: MemberRole
    status: str
    joined_at: datetime


class MembershipWithUserResponse(MembershipResponse):
    """Membership record with embedded user details (for member list endpoints)."""

    user: UserResponse


class MemberRoleUpdate(BaseModel):
    """Payload for changing a member's role."""

    role: MemberRole
