from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def postgres_url_with_driver(value: str, driver: str) -> str:
    """Adapt provider PostgreSQL URLs for SQLAlchemy's explicit drivers."""
    scheme, separator, remainder = value.partition("://")
    if separator and (scheme in {"postgres", "postgresql"} or scheme.startswith("postgresql+")):
        return f"postgresql+{driver}://{remainder}"
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="development", alias="SAWTAI_ENV")
    log_level: str = Field(default="INFO", alias="SAWTAI_LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+asyncpg://sawtai:change-me-for-local-development@postgres:5432/sawtai",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
