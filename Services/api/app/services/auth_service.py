import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.core.security import verify_password, get_password_hash, create_access_token
from app.schemas.auth import UserCreate
from app.models.user import User 

logger = logging.getLogger(__name__)

class AuthService:
    @staticmethod
    def register_user(user_in: UserCreate, db: Session):
        # Synchronous query execution
        existing_user = db.query(User).filter(User.email == user_in.email).first()
        
        if existing_user:
            logger.warning("User Registration Failed : Email Already Exist")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists"
            )
        
        password_hash = get_password_hash(user_in.password)
        
        new_user = User(
            name=user_in.name, 
            email=user_in.email,
            password_hash=password_hash,
            status="pending"
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info("User Registration Successfull.", extra = {"user_id" : new_user.id})
        return {"status": "User Created Successfully"}

    @staticmethod
    def authenticate_user(email: str, password: str, db: Session) -> str:
        user = db.query(User).filter(User.email == email).first()
        
        if not user or not verify_password(password, user.password_hash):
            logger.warning("Login failed : Invalid Password or Username")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.info("user login successfull", extra = {"user_id" : user.id})
        return create_access_token(subject=user.id)
