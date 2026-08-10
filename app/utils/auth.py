from datetime import datetime, timedelta, timezone
from typing import Any
from jose import JWTError, jwt
from app.core.config import get_settings

settings = get_settings()

import hashlib
import os

def hash_password(password: str) -> str:
    """Hash a password using PBKDF2 with SHA-256 and a random salt."""
    salt = os.urandom(16)
    iterations = 100000
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{salt.hex()}:{key.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored hashed version."""
    try:
        salt_hex, key_hex = hashed_password.split(":")
        salt = bytes.fromhex(salt_hex)
        stored_key = bytes.fromhex(key_hex)
        iterations = 100000
        new_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return new_key == stored_key
    except Exception:
        return False

def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    """Generate a JWT token for the user subject."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )
    
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return encoded_jwt

def decode_access_token(token: str) -> str | None:
    """Decode and extract the subject from a JWT token."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload.get("sub")
    except JWTError:
        return None
