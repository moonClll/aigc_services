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
    aigc_base_url: str
    agent_worker_id: str
    agent_model_name: str
    agent_poll_interval_seconds: int = 2
    agent_heartbeat_interval_seconds: int = 20
    agent_lease_seconds: int = 300
    agent_request_timeout_seconds: int = 30
    vivo_api_url: str
    vivo_app_key: str | None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
