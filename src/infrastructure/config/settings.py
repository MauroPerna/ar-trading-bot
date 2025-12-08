from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[3] / ".env"  # noqa: E402
load_dotenv(dotenv_path=ENV_PATH)  # noqa: E402

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, ValidationInfo
from typing import List, Optional, Literal
from enum import Enum
import logging


logger = logging.getLogger(__name__)


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    # ============= DATABASE =============
    db_url: str = Field(
        ...,
        description="PostgreSQL connection URL"
    )
    db_pool_size: int = Field(
        default=5,
        ge=1,
        le=50
    )
    db_max_overflow: int = Field(
        default=10,
        ge=0,
        le=100
    )
    db_pool_timeout: int = Field(
        default=30,
        ge=1
    )
    db_pool_recycle: int = Field(
        default=3600,
        description="Recycle connections after N seconds"
    )
    db_echo: bool = Field(
        default=False,
        description="Log all SQL statements"
    )

    # ============= APPLICATION =============
    app_name: str = Field(default="Trading API")
    app_version: str = Field(default="1.0.0")
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    debug: bool = Field(default=False)

    # ============= API =============
    api_prefix: str = Field(default="/api")
    api_v1_prefix: str = Field(default="/api/v1")

    # ============= LOGGING =============
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # ============= SECURITY (para futuro) =============
    secret_key: Optional[str] = Field(default=None)
    access_token_expire_minutes: int = Field(default=30)

    # ============= CORS =============
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000"
    )
    cors_allow_credentials: bool = Field(default=True)
    cors_allow_methods: List[str] = Field(default=["*"])
    cors_allow_headers: List[str] = Field(default=["*"])

    # ============= SCHEDULER  =============
    scheduler_enabled: bool = Field(default=True)
    scheduler_timezone: str = Field(default="UTC")

    # ============ IOL CREDENTIALS =============
    iol_username: str = Field(
        ...,
        description="IOL Broker Username"
    )
    iol_password: str = Field(
        ...,
        description="IOL Broker Password"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        validate_default=True,
        env_prefix="",
    )

    # ============= COMPUTED PROPERTIES =============
    @property
    def database_url(self) -> str:
        return self.db_url

    @property
    def async_database_url(self) -> str:
        if "postgresql://" in self.db_url:
            return self.db_url.replace("postgresql://", "postgresql+asyncpg://")
        elif "postgresql+psycopg://" in self.db_url:
            return self.db_url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
        return self.db_url

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        return self.environment == Environment.TESTING

    # ============= VALIDATORS =============
    @field_validator("db_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("Database URL cannot be empty")
        if not any(v.startswith(prefix) for prefix in ["postgresql://", "postgresql+asyncpg://", "postgresql+psycopg://"]):
            raise ValueError("Database URL must be a valid PostgreSQL URL")
        return v

    def get_logging_config(self) -> dict:
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": self.log_format
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": self.log_level,
                }
            },
            "root": {
                "level": self.log_level,
                "handlers": ["console"]
            },
            "loggers": {
                "uvicorn": {
                    "level": self.log_level,
                    "handlers": ["console"],
                    "propagate": False
                },
                "sqlalchemy": {
                    "level": "WARNING" if not self.db_echo else "INFO",
                    "handlers": ["console"],
                    "propagate": False
                },
                "sqlalchemy.engine": {
                    "level": "INFO" if self.db_echo else "WARNING",
                    "handlers": ["console"],
                    "propagate": False
                }
            }
        }


settings = Settings()
