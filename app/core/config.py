from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_ignore_empty=True,
    )

    # Telegram
    BOT_TOKEN: str
    WEBHOOK_URL: Optional[str] = None

    # Allowed users (empty = all allowed)
    ALLOWED_USER_IDS: list[int] = []

    # Database
    DATABASE_URL: str = "postgres://disco_user:disco_pass@localhost:5432/disco_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    WHISPER_MODEL: str = "whisper-1"

    # App
    DEBUG: bool = False
    MAX_SKILL_RESPONSES: int = 4

    @field_validator("ALLOWED_USER_IDS", mode="before")
    @classmethod
    def parse_user_ids(cls, v: str | list) -> list[int]:
        if isinstance(v, list):
            return v
        if not v:
            return []
        return [int(x.strip()) for x in str(v).split(",") if x.strip()]


settings = Settings()
