import re
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL

MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    app_name: str = "StockSense"
    # Defaults to the safe choice: only "development" may log reset tokens.
    environment: Literal["development", "test", "production"] = "production"
    debug: bool = False

    postgres_user: str = "stocksense"
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "stocksense"
    # Full URL override (DATABASE_URL); takes precedence over the POSTGRES_* parts.
    # Hosted providers hand out postgres:// or postgresql://; both are normalized
    # to the psycopg 3 driver (see normalize_database_url).
    database_url_override: str | None = Field(default=None, validation_alias="DATABASE_URL")

    # Required (no default). Set SECRET_KEY in the environment or .env.
    # Browser origins allowed to call the API, comma-separated in the environment
    # (e.g. CORS_ORIGINS=http://localhost:5173,https://app.example.com). Empty
    # (the default) disables CORS entirely; "*" is rejected.
    cors_origins: Annotated[list[str], NoDecode] = []
    # Optional regex for preview deployments, e.g. https://.*\.vercel\.app
    cors_origin_regex: str | None = None

    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    password_reset_expire_minutes: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            value = [item for item in value.split(",")]
        if not isinstance(value, list):
            return value
        origins = [str(item).strip().rstrip("/") for item in value if str(item).strip()]
        for origin in origins:
            if origin == "*" or not origin.startswith(("http://", "https://")):
                raise ValueError(
                    f"invalid CORS origin {origin!r}: use explicit http(s)://host[:port] origins"
                )
        return origins

    @field_validator("cors_origin_regex")
    @classmethod
    def valid_cors_origin_regex(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid CORS_ORIGIN_REGEX: {exc}") from None
        return value

    @field_validator("database_url_override")
    @classmethod
    def normalize_database_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @field_validator("secret_key")
    @classmethod
    def secret_key_is_strong(cls, value: str) -> str:
        if len(value) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters; "
                'generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password or None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    @property
    def DATABASE_URL(self) -> str:  # noqa: N802 - name the develop scaffold used
        """Alias of `database_url` kept so scaffold-style code keeps working."""
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
