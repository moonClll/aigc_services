from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os

import jwt
from fastapi import HTTPException, status

from app.core.config import settings

PBKDF2_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iteration_str, salt_hex, digest_hex = encoded_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iteration_str)
        expected_digest = bytes.fromhex(digest_hex)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    ttl = expires_minutes or settings.access_token_expire_minutes
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    payload = {"sub": subject, "exp": expire_at}
    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.token_algorithm,
    )


def decode_access_token(token: str) -> str:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
    )

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.token_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise credentials_error from exc

    subject = payload.get("sub")
    if not subject:
        raise credentials_error
    return subject
