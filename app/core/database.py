import logging

import redis.asyncio as aioredis
from tortoise import Tortoise

from app.core.config import settings

logger = logging.getLogger(__name__)

TORTOISE_ORM = {
    "connections": {
        "default": settings.DATABASE_URL,
    },
    "apps": {
        "models": {
            "models": [
                "app.models.user",
                "app.models.dialog",
                "app.models.stats",
                "app.models.raw_message",
                "aerich.models",
            ],
            "default_connection": "default",
        },
    },
}

_redis: aioredis.Redis | None = None


async def init_db() -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas(safe=True)
    logger.info("Database connected: %s", settings.DATABASE_URL.split("@")[-1])


async def close_db() -> None:
    await Tortoise.close_connections()


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.get_redis_url(), decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
