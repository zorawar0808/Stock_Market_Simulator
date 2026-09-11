"""
Centralized, environment-based configuration.

Nothing in this codebase should read os.environ directly outside of this file —
all runtime configuration (DB URLs, secrets, game defaults) flows through the
`Settings` singleton below so it's auditable in one place and easy to override
per-environment (local / staging / production).
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / ".env", extra="ignore")

    # Database
    database_url: str
    database_url_sync: str

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]
        return url

    # Auth
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 720
    refresh_token_expire_days: int = 7

    # Game defaults — organizer-configurable via admin console; these are only
    # the bootstrap defaults used when a team/market is first created.
    default_starting_capital: float = 10000.0
    default_max_team_members: int = 3
    price_tick_interval_seconds: int = 4

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
