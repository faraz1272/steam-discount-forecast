from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    APP_ENV: str = "dev"
    OPENAI_API_KEY: Optional[str] | None = None
    OPENAI_MODEL: str = "gpt-4.1-mini"
    ITAD_API_KEY: Optional[str] | None = None
    ITAD_BASE_URL: str = "https://api.isthereanydeal.com"
    RAWG_API_KEY: Optional[str] | None = None
    MODEL_30D_PATH: str = "/app/artifacts/30d"
    MODEL_60D_PATH: str = "/app/artifacts/60d"
    FEATURES_PATH: str = "/app/artifacts/feature_names.json"
    NEWS_API_KEY: Optional[str] | None = None
    NEWS_API_BASE_URL: str = "https://newsapi.org/v2"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# This creates a single global settings object
settings = Settings()