from fastapi import Header, HTTPException, status

from app.core.config import settings


def verify_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    required = settings.backend_callback_token
    if not required:
        return
    if x_internal_token != required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token",
        )

