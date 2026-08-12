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
    jwt_secret: str = Field(
        default="local-only-insecure-jwt-secret-change-before-production",
        alias="JWT_SECRET",
    )
    access_token_minutes: int = Field(default=30, alias="ACCESS_TOKEN_MINUTES")
    refresh_token_days: int = Field(default=7, alias="REFRESH_TOKEN_DAYS")
    tenant_pepper: str = Field(
        default="local-only-insecure-tenant-pepper",
        alias="TENANT_PEPPER",
    )
    pii_encryption_key: str = Field(
        default="local-only-insecure-pii-encryption-key",
        alias="PII_ENCRYPTION_KEY",
    )
    object_store_endpoint: str = Field(default="", alias="MINIO_ENDPOINT")
    object_store_access_key: str = Field(default="", alias="MINIO_ROOT_USER")
    object_store_secret_key: str = Field(default="", alias="MINIO_ROOT_PASSWORD")
    object_store_bucket: str = Field(default="sawtai-media", alias="MINIO_MEDIA_BUCKET")
    object_store_local_root: str = Field(default="/tmp/sawtai-objects", alias="OBJECT_STORE_LOCAL_ROOT")
    document_max_upload_bytes: int = Field(default=15_728_640, alias="DOCUMENT_MAX_UPLOAD_BYTES")
    document_max_pages: int = Field(default=250, alias="DOCUMENT_MAX_PAGES")
    encoders_url: str = Field(default="http://encoders:8001", alias="ENCODERS_URL")
    rag_encoder_mode: Literal["fallback", "remote"] = Field(default="fallback", alias="RAG_ENCODER_MODE")
    rag_encoder_timeout_seconds: float = Field(default=8.0, alias="RAG_ENCODER_TIMEOUT_SECONDS")
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
    rag_hybrid_gate: float = Field(default=0.18, alias="RAG_HYBRID_GATE")


@lru_cache
def get_settings() -> Settings:
    return Settings()
