from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_ENV: str = "dev"
    OPENAI_API_KEY: str | None = None
    ITAD_API_KEY: str | None = None
    RAWG_API_KEY: str | None = None
    MODEL_30D_PATH: str
    MODEL_60D_PATH: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# This creates a single global settings object
settings = Settings()