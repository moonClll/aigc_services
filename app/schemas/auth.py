from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=8, max_length=32)
    display_name: str | None = Field(default=None, max_length=128)


class UserProfile(BaseModel):
    id: int
    username: str
    display_name: str | None
    status: str

    model_config = ConfigDict(from_attributes=True)


class LoginData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile
