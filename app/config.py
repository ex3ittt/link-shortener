from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./links.db"
    # Empty means "no Redis": cache and rate limits live in process memory.
    redis_url: str = ""
    base_url: str = "http://localhost:8000"
    create_limit_per_minute: int = 20
    code_length: int = 7
    cache_ttl_seconds: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
