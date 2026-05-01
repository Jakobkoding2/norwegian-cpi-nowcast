from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    kassal_api_key: str
    kassal_base_url: str = "https://kassal.app/api/v1"

    # Request tuning
    request_timeout: float = 15.0
    max_concurrency: int = 4   # Kassal free tier: ~60 req/min; 4 concurrent keeps us safe
    retry_attempts: int = 3
    retry_wait_seconds: float = 2.0


settings = Settings()  # type: ignore[call-arg]
