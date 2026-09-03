from pathlib import Path
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    app_name: str = "Vector"
    env: str = "local"

    database_url: str
    redis_url: str

    groq_api_key: str
    tavily_api_key: str = ""
    tavily_cover_letter_api_key: str = ""

    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=ROOT_ENV, extra="ignore")

    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "./data")

settings = Settings()