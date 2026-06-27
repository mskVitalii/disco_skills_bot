import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

# from app.bot.keyboards.inline import dialog_keyboard
# from app.bot.states import DialogState
# from app.core.config import settings
# from app.services.ai_service import transcribe_voice
# from app.services.dialog_service import (
#     get_or_create_user,
#     handle_user_message,
#     update_node_message_id,
# )

logger = logging.getLogger(__name__)
router = Router(name="messages")


# ─── Ping-pong (временно, пока отлаживаем Railway) ───────────────────────────

@router.message(F.text)
async def handle_ping_pong(message: Message) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    logger.info("echo user_id=%s text=%r", message.from_user.id, text[:80])
    await message.answer(text)


# ─── Оригинальные обработчики (AI-пайплайн) ──────────────────────────────────

# def _is_allowed(telegram_id: int) -> bool:
#     if not settings.ALLOWED_USER_IDS:
#         return True
#     return telegram_id in settings.ALLOWED_USER_IDS
#
#
# async def _get_or_init_user(message: Message):
#     return await get_or_create_user(
#         telegram_id=message.from_user.id,
#         chat_id=message.chat.id,
#         username=message.from_user.username,
#         first_name=message.from_user.first_name or "",
#     )
#
#
# async def _process_text(message: Message, text: str, state: FSMContext) -> None:
#     user = await _get_or_init_user(message)
#
#     thinking = await message.answer("⏳")
#
#     text_response, ai_result, node_id = await handle_user_message(
#         user=user,
#         user_message=text,
#     )
#
#     kb = dialog_keyboard(ai_result, node_id, show_back=True)
#
#     await thinking.delete()
#     sent = await message.answer(text_response, parse_mode="HTML", reply_markup=kb)
#     await update_node_message_id(node_id, sent.message_id)
#
#     await state.set_state(DialogState.active)
#
#
# # ─── Text message ─────────────────────────────────────────────────────────────
#
# @router.message(F.text, DialogState.active)
# async def handle_text_active(message: Message, state: FSMContext) -> None:
#     if not _is_allowed(message.from_user.id):
#         return
#     text = (message.text or "").strip()
#     if not text or text.startswith("/"):
#         return
#     logger.info("text user_id=%s len=%d", message.from_user.id, len(text))
#     await _process_text(message, text, state)
#
#
# # Auto-activate for users who skipped /start
# @router.message(F.text)
# async def handle_text_any(message: Message, state: FSMContext) -> None:
#     if not _is_allowed(message.from_user.id):
#         return
#     text = (message.text or "").strip()
#     if not text or text.startswith("/"):
#         return
#
#     current = await state.get_state()
#     if current == DialogState.waiting_scene:
#         return  # handled by command handler
#
#     logger.info("text(any) user_id=%s len=%d", message.from_user.id, len(text))
#     await _process_text(message, text, state)
#
#
# # ─── Voice message ────────────────────────────────────────────────────────────
#
# @router.message(F.voice)
# async def handle_voice(message: Message, state: FSMContext) -> None:
#     if not _is_allowed(message.from_user.id):
#         return
#
#     voice = message.voice
#     if not voice:
#         return
#
#     logger.info("voice user_id=%s duration=%ds", message.from_user.id, voice.duration)
#     thinking = await message.answer("🎙️ Транскрибирую голосовое...")
#
#     bot = message.bot
#     file = await bot.get_file(voice.file_id)
#     file_bytes = await bot.download_file(file.file_path)
#     audio_bytes = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)
#
#     transcribed = await transcribe_voice(audio_bytes, "voice.ogg")
#     await thinking.delete()
#
#     if not transcribed:
#         await message.answer("Не удалось распознать голосовое.")
#         return
#
#     await message.answer(f"<i>Распознано:</i> {transcribed}", parse_mode="HTML")
#     await _process_text(message, transcribed, state)
#
#
# # ─── Video note (кружочек) ────────────────────────────────────────────────────
#
# @router.message(F.video_note)
# async def handle_video_note(message: Message, state: FSMContext) -> None:
#     if not _is_allowed(message.from_user.id):
#         return
#
#     video_note = message.video_note
#     if not video_note:
#         return
#
#     logger.info("video_note user_id=%s duration=%ds", message.from_user.id, video_note.duration)
#     thinking = await message.answer("🎙️ Транскрибирую кружочек...")
#
#     bot = message.bot
#     file = await bot.get_file(video_note.file_id)
#     file_bytes = await bot.download_file(file.file_path)
#     audio_bytes = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)
#
#     transcribed = await transcribe_voice(audio_bytes, "video_note.mp4")
#     await thinking.delete()
#
#     if not transcribed:
#         await message.answer("Не удалось распознать кружочек.")
#         return
#
#     await message.answer(f"<i>Распознано:</i> {transcribed}", parse_mode="HTML")
#     await _process_text(message, transcribed, state)
