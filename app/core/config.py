from typing import Any, Optional, Tuple, Type
from pydantic import field_validator
from pydantic_settings import BaseSettings, EnvSettingsSource, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources.providers.dotenv import DotEnvSettingsSource


def _lenient_decode(self, field_name: str, field: Any, value: Any) -> Any:
    try:
        return super(type(self), self).decode_complex_value(field_name, field, value)
    except Exception:
        return value


class _LenientEnvSource(EnvSettingsSource):
    decode_complex_value = _lenient_decode


class _LenientDotEnvSource(DotEnvSettingsSource):
    decode_complex_value = _lenient_decode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_ignore_empty=True,
        extra="ignore",
    )

    # Telegram
    BOT_TOKEN: str
    WEBHOOK_URL: Optional[str] = None

    # Owner ID — bot ignores owner's own messages in business chats (respond only to /disco)
    BOT_OWNER_ID: Optional[int] = None

    # Database
    DATABASE_URL: str = "postgres://disco_user:disco_pass@localhost:5432/disco_db"

    # Redis — individual vars from Railway Redis plugin take priority over REDIS_URL
    REDISHOST: Optional[str] = None
    REDISPORT: int = 6379
    REDISPASSWORD: Optional[str] = None
    REDIS_URL: str = "redis://localhost:6379"

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    WHISPER_MODEL: str = "whisper-1"

    # App
    DEBUG: bool = False
    MAX_SKILL_RESPONSES: int = 4
    ADMIN_TOKEN: Optional[str] = None
    # Probability [0..1] that the bot chimes in on a business message (not every message)
    ACTIVATION_CHANCE: float = 0.40

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_db_scheme(cls, v: str) -> str:
        # Tortoise ORM requires "postgres://" — Railway and some providers use "postgresql://"
        return v.replace("postgresql://", "postgres://", 1) if isinstance(v, str) else v

    def get_redis_url(self) -> str:
        """Build Redis URL from individual Railway plugin vars if available."""
        if self.REDISHOST:
            if self.REDISPASSWORD:
                return f"redis://:{self.REDISPASSWORD}@{self.REDISHOST}:{self.REDISPORT}"
            return f"redis://{self.REDISHOST}:{self.REDISPORT}"
        return self.REDIS_URL

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        **kwargs: Any,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, _LenientEnvSource(settings_cls), _LenientDotEnvSource(settings_cls), *kwargs.values())


settings = Settings()
