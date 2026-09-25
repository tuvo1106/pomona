from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "POMONA_"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_file=".env", extra="ignore")

    db_path: Path = Path("data/health.db")
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
