"""Password hashing and JWT token helpers.

Passwords are hashed with PBKDF2-HMAC-SHA256 (salted, per-user). JWT access
tokens are signed with the app's secret key and carry the user's email as
the ``sub`` claim.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

_PBKDF2_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2 with SHA-256 and a random salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"{salt.hex()}:{key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored hashed version.

    Uses a constant-time comparison (``hmac.compare_digest``) so that
    response timing can't leak how many leading bytes of the hash matched —
    a plain ``==`` on bytes short-circuits on the first mismatch and is a
    known timing side-channel for secret comparisons.
    """
    try:
        salt_hex, key_hex = hashed_password.split(":")
        salt = bytes.fromhex(salt_hex)
        stored_key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
        )
        return hmac.compare_digest(new_key, stored_key)
    except (ValueError, TypeError):
        # Malformed stored hash (wrong format, bad hex) -> treat as no match.
        return False


def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    """Generate a signed JWT token for the given user subject (email)."""
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode = {"exp": expire, "sub": str(subject)}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Decode a JWT and return its subject, or ``None`` if invalid/expired."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload.get("sub")
    except JWTError:
        return None
        