from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.schemas.auth import UserCreate, Token
from app.services.auth_service import AuthService
from app.db.database import get_db  # Imported from your file

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    return AuthService.register_user(user_in=user_in, db=db)

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    access_token = AuthService.authenticate_user(
        email=form_data.username, 
        password=form_data.password, 
        db=db
    )
    return {"access_token": access_token, "token_type": "bearer"}
