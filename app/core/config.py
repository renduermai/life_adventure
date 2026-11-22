"""Environment configuration. Secrets are never included in public status."""
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[2]


def postgres_url(value: str) -> URL:
    """Normalize the driver and require encrypted remote connections."""
    try:
        url = make_url(value)
        if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError()
        if not url.host or not url.database or not url.username:
            raise ValueError()
        if url.host not in {"localhost", "127.0.0.1", "::1"}:
            if url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
                raise ValueError()
        return url.set(drivername="postgresql+psycopg")
    except Exception:
        raise ValueError("需要完整 PostgreSQL URL；远程连接须启用 sslmode=require 或更严格验证") from None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore",
        hide_input_in_errors=True,
    )
    app_name: str = "人生冒险之旅"
    app_timezone: str = "Asia/Shanghai"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    ai_encryption_keys: SecretStr | None = None
    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
    supabase_anon_key: SecretStr | None = None
    supabase_secret_key: SecretStr | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_storage_bucket: str | None = None
    memory_backup_dir: Path | None = None
    memory_backup_key: SecretStr | None = None

    @field_validator("database_url", "migration_database_url", mode="before")
    @classmethod
    def empty_url(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def validate_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            postgres_url(value.get_secret_value())
        return value

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("需要有效的 IANA 时区") from None
        return value


def load_settings() -> Settings:
    try:
        return Settings()
    except Exception:
        # Do not echo connection strings in startup tracebacks.
        raise RuntimeError("配置无效，请检查 .env 中的时区、日志级别和 PostgreSQL 连接格式") from None
