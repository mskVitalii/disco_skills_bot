import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Update
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
_init_task: asyncio.Task | None = None
_bot_username: str | None = None
_ready: bool = False


async def _background_init() -> None:
    global _polling_task, _bot_username, _ready

    for attempt in range(30):
        try:
            await init_db()
            logger.info("Database connected")
            break
        except Exception as exc:
            logger.warning("DB not ready (attempt %d/30): %s", attempt + 1, exc)
            if attempt < 29:
                await asyncio.sleep(3)
            else:
                logger.error("DB connection failed after 30 attempts — giving up")
                return

    try:
        me = await bot.get_me()
        _bot_username = me.username
        logger.info("Bot ready: @%s (id=%d)", me.username, me.id)
    except Exception as exc:
        logger.error("Failed to get bot info: %s", exc)
        return

    if settings.WEBHOOK_URL:
        webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook"
        try:
            await bot.set_webhook(webhook_url, drop_pending_updates=True)
            logger.info("Webhook set: %s", webhook_url)
        except Exception as exc:
            logger.error("Failed to set webhook: %s", exc)
            return
    else:
        _polling_task = asyncio.create_task(_run_polling())
        logger.info("Polling started")

    _ready = True
    logger.info("Init complete — allowed_users=%s", settings.ALLOWED_USER_IDS or "all")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _init_task
    # Background init so health endpoint responds immediately
    _init_task = asyncio.create_task(_background_init())
    yield

    if _init_task and not _init_task.done():
        _init_task.cancel()
        try:
            await _init_task
        except asyncio.CancelledError:
            pass

    if _polling_task:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass

    if settings.WEBHOOK_URL and _ready:
        try:
            await bot.delete_webhook()
        except Exception:
            pass

    for coro in (bot.session.close(), storage.close(), close_db(), close_redis()):
        try:
            await coro
        except Exception:
            pass

    logger.info("Shutdown complete")


async def _run_polling() -> None:
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="Disco Skills Bot", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info("%s %s → %d (%.1fms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.post("/webhook")
async def webhook(request: Request) -> dict:
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot=bot, update=update)
    return {"ok": True}


@app.get("/health")
async def health() -> JSONResponse:
    status = "ok" if _ready else "starting"
    return JSONResponse({"status": status, "bot": _bot_username})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
