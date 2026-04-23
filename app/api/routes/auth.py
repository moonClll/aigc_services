import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.response import ok
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import LoginData, LoginRequest, RegisterRequest, UserProfile

router = APIRouter(prefix="/auth", tags=["Auth"])

USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,19}$")
SPECIAL_PATTERN = re.compile(r"[^A-Za-z0-9]")


def _validate_register_payload(payload: RegisterRequest) -> list[str]:
    errors: list[str] = []

    if not USERNAME_PATTERN.fullmatch(payload.username):
        errors.append(
            "username: 4-20 chars, starts with a letter, only letters/numbers/underscore"
        )




    password = payload.password
    if len(password) < 8 or len(password) > 32:
        errors.append("password: length must be 8-32")
    if not any(char.isupper() for char in password):
        errors.append("password: must include at least one uppercase letter")
    if not any(char.islower() for char in password):
        errors.append("password: must include at least one lowercase letter")
    if not any(char.isdigit() for char in password):
        errors.append("password: must include at least one digit")
    if not SPECIAL_PATTERN.search(password):
        errors.append("password: must include at least one special character")

    return errors


@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    rules_errors = _validate_register_payload(payload)
    if rules_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "\u8d26\u53f7\u6216\u5bc6\u7801\u683c\u5f0f\u4e0d\u7b26\u5408\u8981\u6c42",
                "rules": rules_errors,
            },
        )

    existed = db.scalar(select(User).where(User.username == payload.username))
    if existed is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="\u8d26\u53f7\u5df2\u5b58\u5728",
        )

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=(payload.display_name or payload.username).strip(),
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return ok(UserProfile.model_validate(user).model_dump(), "\u6ce8\u518c\u6210\u529f")


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="\u8d26\u6237\u6216\u5bc6\u7801\u9519\u8bef",
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="\u8d26\u6237\u6216\u5bc6\u7801\u9519\u8bef",
        )

    token = create_access_token(str(user.id))
    profile = UserProfile.model_validate(user)
    data = LoginData(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=profile,
    )
    return ok(data.model_dump(), "Login success")

