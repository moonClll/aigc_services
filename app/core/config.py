from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Learning App Service"
    api_v1_prefix: str = "/api/v1"
    secret_key: str = "please-change-this-in-env"
    access_token_expire_minutes: int = 60 * 24
    token_algorithm: str = "HS256"
    backend_callback_token: str | None = None
    backend_task_lease_seconds: int = 300
    database_url: str = (
        "mysql+pymysql://root:123456@127.0.0.1:3306/learning_app?charset=utf8mb4"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
