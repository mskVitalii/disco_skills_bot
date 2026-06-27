import logging

from aiogram import F, Router
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router(name="messages")


@router.message(F.text)
async def handle_ping_pong(message: Message) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    logger.info("echo user_id=%s text=%r", message.from_user.id, text[:80])
    await message.answer(text)
