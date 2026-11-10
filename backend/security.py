from datetime import datetime, timedelta

from jose import JWTError, jwt
from pwdlib import PasswordHash

from .config import get_settings


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, password_digest: str) -> bool:
    return password_hash.verify(password, password_digest)


def create_token(user_id: str) -> str:
    settings = get_settings()
    expires = datetime.utcnow() + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": user_id, "exp": expires}, settings.jwt_secret, algorithm="HS256")


def read_token(token: str) -> str:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
        subject = payload.get("sub")
        if not subject:
            raise ValueError("Token subject is missing")
        return subject
    except (JWTError, ValueError) as error:
        raise ValueError("Invalid or expired token") from error
