from functools import lru_cache
from typing import Literal

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
    tenant_pepper: str = Field(
        default="local-only-insecure-tenant-pepper",
        alias="TENANT_PEPPER",
    )
    pii_encryption_key: str = Field(
        default="local-only-insecure-pii-encryption-key",
        alias="PII_ENCRYPTION_KEY",
    )
    whatsapp_verify_token: str = Field(default="", alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_app_secret: str = Field(default="", alias="WHATSAPP_APP_SECRET")
    whatsapp_access_token: str = Field(default="", alias="WHATSAPP_ACCESS_TOKEN")
    whatsapp_phone_number_id: str = Field(default="", alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_graph_base_url: str = Field(
        default="https://graph.facebook.com",
        alias="WHATSAPP_GRAPH_BASE_URL",
    )
    whatsapp_graph_version: str = Field(default="v23.0", alias="WHATSAPP_GRAPH_VERSION")
    whatsapp_tenant_code: str = Field(default="shj-demo", alias="WHATSAPP_TENANT_CODE")
    whatsapp_source_handle: str = Field(
        default="demo-whatsapp",
        alias="WHATSAPP_SOURCE_HANDLE",
    )
    whatsapp_signature_required: bool = Field(
        default=True,
        alias="WHATSAPP_SIGNATURE_REQUIRED",
    )
    whatsapp_delivery_mode: Literal["simulate", "live"] = Field(
        default="simulate",
        alias="WHATSAPP_DELIVERY_MODE",
    )
    whatsapp_reply_mode: Literal["off", "acknowledge", "draft"] = Field(
        default="draft",
        alias="WHATSAPP_REPLY_MODE",
    )
    rag_lexical_gate: float = Field(default=0.18, alias="RAG_LEXICAL_GATE")


@lru_cache
def get_settings() -> Settings:
    return Settings()
