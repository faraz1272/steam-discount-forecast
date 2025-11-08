from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_ENV: str = "dev"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4.1-mini"
    ITAD_API_KEY: str | None = None
    ITAD_BASE_URL: str = "https://api.isthereanydeal.com/games/info/v2"
    RAWG_API_KEY: str | None = None
    MODEL_30D_PATH: str
    MODEL_60D_PATH: str
    FEATURES_PATH: str
    NEWS_API_KEY: str | None = None
    NEWS_API_BASE_URL: str = "https://newsapi.org/v2"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# This creates a single global settings object
settings = Settings()