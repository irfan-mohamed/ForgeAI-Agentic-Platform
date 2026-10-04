from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse


router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Returns the authenticated user's own profile.

    ``password_hash`` is excluded by the UserResponse schema.
    """
    return current_user