import logging
import random
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards.inline import dialog_keyboard, enumeration_keyboard
from app.bot.states import DialogState
from app.core.config import settings
from app.models.raw_message import RawMessage
from app.services.ai_service import transcribe_voice
from app.services.dialog_service import (
    get_or_create_user,
    get_current_context_message,
    handle_user_message,
    update_node_message_id,
)

_NUMBERED_RE = re.compile(r'^\s*\d+[.)]\s+(.+)$')
_BULLET_RE = re.compile(r'^\s*[-•*]\s+(.+)$')


def _detect_enumeration(text: str) -> list[str] | None:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return None
    # Allow one optional header line before the list (e.g. "Дай мне память:")
    start = 0
    if not (_NUMBERED_RE.match(lines[0]) or _BULLET_RE.match(lines[0])):
        start = 1
    items: list[str] = []
    for line in lines[start:]:
        m = _NUMBERED_RE.match(line)
        if m:
            items.append(m.group(1).strip())
            continue
        m = _BULLET_RE.match(line)
        if m:
            items.append(m.group(1).strip())
            continue
        return None  # non-list line inside list body breaks the pattern
    return items if len(items) >= 2 else None

logger = logging.getLogger(__name__)
router = Router(name="messages")


def _is_owner(telegram_id: int) -> bool:
    return settings.BOT_OWNER_ID is not None and telegram_id == settings.BOT_OWNER_ID


async def _get_or_init_user(message: Message):
    return await get_or_create_user(
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name or "",
    )


async def _log_raw(
    message: Message,
    message_type: str,
    text: str | None = None,
    business_connection_id: str | None = None,
) -> None:
    uid = message.from_user.id if message.from_user else 0
    try:
        await RawMessage.create(
            telegram_id=uid,
            chat_id=message.chat.id,
            username=message.from_user.username if message.from_user else None,
            message_id=message.message_id,
            message_type=message_type,
            text=text,
            business_connection_id=business_connection_id,
        )
    except Exception:
        logger.exception("Failed to save raw_message user_id=%s type=%s", uid, message_type)


async def _process_enum(message: Message, items: list[str], state: FSMContext) -> None:
    await state.update_data(pending_enum=items)
    await state.set_state(DialogState.active)
    text_lines = "\n".join(f"  {i + 1}. {item}" for i, item in enumerate(items))
    header = "<i>Выбери путь:</i>"
    await message.answer(
        f"{header}\n{text_lines}",
        parse_mode="HTML",
        reply_markup=enumeration_keyboard(items),
    )


async def _process_text(message: Message, text: str, state: FSMContext) -> None:
    items = _detect_enumeration(text)
    if items:
        await _process_enum(message, items, state)
        return

    thinking = None
    try:
        user = await _get_or_init_user(message)
        thinking = await message.answer("⏳")
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass

        text_response, ai_result, node_id = await handle_user_message(
            user=user,
            user_message=text,
        )

        if not ai_result.skill_responses:
            try:
                await thinking.delete()
            except Exception:
                pass
            return

        kb = dialog_keyboard(ai_result, node_id, show_back=True)
        try:
            sent = await thinking.edit_text(text_response, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest:
            try:
                await thinking.delete()
            except Exception:
                pass
            sent = await message.answer(text_response, parse_mode="HTML", reply_markup=kb)
        await update_node_message_id(node_id, sent.message_id)
        await state.set_state(DialogState.active)
    except Exception:
        logger.exception("Error processing message user_id=%s text=%r", message.from_user.id, text[:80])
        if thinking:
            try:
                await thinking.delete()
            except Exception:
                pass
        await message.answer("Характеристики молчат. Попробуй снова — или /new чтобы начать заново.")


# ─── Text message ─────────────────────────────────────────────────────────────

@router.message(F.text, DialogState.active)
async def handle_text_active(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    logger.info("text user_id=%s len=%d", message.from_user.id, len(text))
    await _log_raw(message, "text", text=text)
    await _process_text(message, text, state)


# Auto-activate for users who skipped /start
@router.message(F.text)
async def handle_text_any(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    current = await state.get_state()
    if current == DialogState.waiting_scene:
        return  # handled by command handler

    logger.info("text(any) user_id=%s len=%d", message.from_user.id, len(text))
    await _log_raw(message, "text", text=text)
    await _process_text(message, text, state)


# ─── Business account messages ───────────────────────────────────────────────

@router.business_message(Command("disco"))
async def handle_business_disco(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    logger.info("business_disco user_id=%s conn=%s", uid, message.business_connection_id)
    await _log_raw(message, "business_disco", text=message.text, business_connection_id=message.business_connection_id)

    user = await get_or_create_user(
        telegram_id=uid,
        chat_id=message.chat.id,
        username=message.from_user.username if message.from_user else None,
        first_name=(message.from_user.first_name or "") if message.from_user else "",
    )

    last_message = await get_current_context_message(user)
    if last_message:
        prompt = f"Характеристики пробуждаются снова. Мысли возвращаются к: «{last_message[:120]}»"
    else:
        prompt = "Детектив молчит. Тишина. Характеристики начинают говорить сами по себе."

    thinking = await message.answer("🎭 Характеристики пробуждаются...")
    text, ai_result, node_id = await handle_user_message(user=user, user_message=prompt)

    if not ai_result.skill_responses:
        try:
            await thinking.delete()
        except Exception:
            pass
        return

    kb = dialog_keyboard(ai_result, node_id, show_back=bool(last_message))
    try:
        sent = await thinking.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        try:
            await thinking.delete()
        except Exception:
            pass
        sent = await message.answer(text, parse_mode="HTML", reply_markup=kb)
    await update_node_message_id(node_id, sent.message_id)
    await state.set_state(DialogState.active)


@router.business_message(F.text)
async def handle_business_text(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else 0
    text = (message.text or "").strip()
    logger.info(
        "business_message user_id=%s conn=%s len=%d text=%r",
        uid, message.business_connection_id, len(text), text[:120],
    )
    if not text or text.startswith("/"):
        return
    await _log_raw(message, "business_text", text=text, business_connection_id=message.business_connection_id)
    # Skip owner's own messages — bot only responds to /disco for the owner
    if _is_owner(uid):
        return
    # Характеристики встревают не в каждое сообщение — только иногда
    if random.random() > settings.ACTIVATION_CHANCE:
        logger.debug("business_message skipped by activation chance user_id=%s", uid)
        return
    await _process_text(message, text, state)


# ─── Voice message ────────────────────────────────────────────────────────────

@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext) -> None:
    voice = message.voice
    if not voice:
        return

    logger.info("voice user_id=%s duration=%ds", message.from_user.id, voice.duration)
    await _log_raw(message, "voice")
    thinking = await message.answer("🎙️ Транскрибирую голосовое...")

    bot = message.bot
    file = await bot.get_file(voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    audio_bytes = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)

    transcribed = await transcribe_voice(audio_bytes, "voice.ogg")
    try:
        await thinking.delete()
    except Exception:
        pass

    if not transcribed:
        await message.answer("Не удалось распознать голосовое.")
        return

    await message.answer(f"<i>Распознано:</i> {transcribed}", parse_mode="HTML")
    await _process_text(message, transcribed, state)


# ─── Video note (кружочек) ────────────────────────────────────────────────────

@router.message(F.video_note)
async def handle_video_note(message: Message, state: FSMContext) -> None:
    video_note = message.video_note
    if not video_note:
        return

    logger.info("video_note user_id=%s duration=%ds", message.from_user.id, video_note.duration)
    await _log_raw(message, "video_note")
    thinking = await message.answer("🎙️ Транскрибирую кружочек...")

    bot = message.bot
    file = await bot.get_file(video_note.file_id)
    file_bytes = await bot.download_file(file.file_path)
    audio_bytes = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)

    transcribed = await transcribe_voice(audio_bytes, "video_note.mp4")
    try:
        await thinking.delete()
    except Exception:
        pass

    if not transcribed:
        await message.answer("Не удалось распознать кружочек.")
        return

    await message.answer(f"<i>Распознано:</i> {transcribed}", parse_mode="HTML")
    await _process_text(message, transcribed, state)
