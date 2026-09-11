import uuid
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

    frontend_origin: str = "http://localhost:3000"

    dev_mode: bool = True
    dev_user_id: uuid.UUID = uuid.UUID("fbf2421e-2961-4e83-941f-af35c60575d5")

    notion_client_id: str = ""
    notion_client_secret: str = ""
    notion_redirect_uri: str = "http://localhost:8000/api/notion/callback"
    notion_webhook_secret: str = ""

    model_config = SettingsConfigDict(env_file=ROOT_ENV, extra="ignore")

    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "./data")

settings = Settings()