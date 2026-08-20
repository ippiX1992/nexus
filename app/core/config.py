from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Nexus API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
    database_migration_url: str = "postgresql+psycopg://nexus:nexus@localhost:5432/nexus"
    jwt_secret: str = Field(default="development-secret-change-me-32-chars", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    two_factor_challenge_minutes: int = 5
    max_active_sessions: int = 10
    allowed_origins: str = "http://localhost:3000"
    cookie_secure: bool = False
    media_root: str = "media"
    @property
    def origins(self) -> list[str]: return [v.strip() for v in self.allowed_origins.split(",") if v.strip()]
@lru_cache
def get_settings() -> Settings: return Settings()
