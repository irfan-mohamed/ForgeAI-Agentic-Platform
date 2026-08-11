from datetime import datetime, timedelta, timezone
from typing import Union, Any
from jose import jwt, JWTError
import bcrypt
from app.core.config import settings



def verify_password(plain_password: str, hashed_password: str) -> bool :
    plain_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(plain_bytes, hashed_bytes)

def get_password_hash(password: str) -> str:
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode('utf-8')  

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta

    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes = settings.ACCESS_TOKEN_EXPIRY_MINUTES)

    to_encode = {"exp" : expire, "sub" : str(subject)}
    encode_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm = settings.ALGORITHM)

    return encode_jwt

def decode_access_token(token: str) -> str:
    try :
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms = [settings.ALGORITHM]
        )

        subject = payload.get("sub")

        if subject is None:
            raise ValueError("Token doesn't contain a Subject")

        return subject

    except JWTError:
        raise ValueError("couldn't validate credentials")