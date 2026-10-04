from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict


class UserResponse(BaseModel):
    """
    Safe public representation of a User.

    Deliberately omits `password_hash` — never return credentials over the wire.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    status: str
    created_at: datetime
    updated_at: datetime
