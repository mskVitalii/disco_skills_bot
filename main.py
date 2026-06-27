import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Update
from fastapi import FastAPI, Request

from app.bot.router import main_router
from app.core.config import settings
from app.core.database import close_db, close_redis, init_db

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Bot & Dispatcher ─────────────────────────────────────────────────────────

bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
storage = RedisStorage.from_url(settings.REDIS_URL)
dp = Dispatcher(storage=storage)
dp.include_router(main_router)

_polling_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _polling_task
    await init_db()
    logger.info("Database initialized")

    if settings.WEBHOOK_URL:
        webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook"
        await bot.set_webhook(webhook_url, drop_pending_updates=True)
        logger.info("Webhook set: %s", webhook_url)
    else:
        _polling_task = asyncio.create_task(_run_polling())
        logger.info("Polling started")

    yield

    if _polling_task:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass

    if settings.WEBHOOK_URL:
        await bot.delete_webhook()

    await bot.session.close()
    await storage.close()
    await close_db()
    await close_redis()
    logger.info("Shutdown complete")


async def _run_polling() -> None:
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="Disco Skills Bot", lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request) -> dict:
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot=bot, update=update)
    return {"ok": True}


@app.get("/")
async def health() -> dict:
    return {"status": "ok", "bot": (await bot.get_me()).username}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
