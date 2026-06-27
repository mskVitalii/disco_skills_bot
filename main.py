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
storage = RedisStorage.from_url(settings.get_redis_url())
dp = Dispatcher(storage=storage)
dp.include_router(main_router)

_polling_task: asyncio.Task | None = None
_init_task: asyncio.Task | None = None
_bot_username: str | None = None
_ready: bool = False


async def _background_init() -> None:
    global _polling_task, _bot_username, _ready

    logger.info("=== Background init started ===")

    # ── PostgreSQL ─────────────────────────────────────────────────────────────
    db_dsn = settings.DATABASE_URL.split("@")[-1]  # hide credentials in logs
    logger.info("[1/4] Connecting to PostgreSQL (%s)...", db_dsn)
    for attempt in range(30):
        try:
            await init_db()
            logger.info("[1/4] PostgreSQL connected on attempt %d", attempt + 1)
            break
        except Exception as exc:
            logger.warning(
                "[1/4] PostgreSQL not ready (attempt %d/30): %s — retrying in 3s",
                attempt + 1, exc,
            )
            if attempt < 29:
                await asyncio.sleep(3)
            else:
                logger.error(
                    "[1/4] FAILED: cannot connect to PostgreSQL (%s) after 30 attempts. "
                    "Check DATABASE_URL and that the DB service is running.",
                    db_dsn,
                )
                return

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis_url = settings.get_redis_url()
    redis_url_safe = redis_url.split("@")[-1] if "@" in redis_url else redis_url
    logger.info("[2/4] Checking Redis (%s)...", redis_url_safe)
    try:
        from app.core.database import get_redis
        redis = get_redis()
        await redis.ping()
        logger.info("[2/4] Redis OK")
    except Exception as exc:
        logger.error(
            "[2/4] FAILED: cannot reach Redis (%s): %s. "
            "Check REDIS_URL and that the Redis service is running.",
            redis_url_safe, exc,
        )
        return

    # ── Telegram Bot API ───────────────────────────────────────────────────────
    logger.info("[3/4] Calling Telegram getMe...")
    try:
        me = await bot.get_me()
        _bot_username = me.username
        logger.info("[3/4] Telegram OK: @%s (id=%d)", me.username, me.id)
    except Exception as exc:
        logger.error(
            "[3/4] FAILED: Telegram getMe failed: %s. "
            "Check BOT_TOKEN and network access to api.telegram.org.",
            exc,
        )
        return

    # ── Webhook / Polling ──────────────────────────────────────────────────────
    if settings.WEBHOOK_URL:
        webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook"
        logger.info("[4/4] Setting webhook: %s", webhook_url)
        try:
            await bot.set_webhook(webhook_url, drop_pending_updates=True)
            logger.info("[4/4] Webhook set")
        except Exception as exc:
            logger.error(
                "[4/4] FAILED: set_webhook failed: %s. "
                "Check WEBHOOK_URL is publicly reachable by Telegram.",
                exc,
            )
            return
    else:
        logger.info("[4/4] No WEBHOOK_URL — starting polling")
        _polling_task = asyncio.create_task(_run_polling())

    _ready = True
    logger.info(
        "=== Init complete === bot=@%s allowed_users=%s",
        _bot_username,
        settings.ALLOWED_USER_IDS or "all",
    )


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
