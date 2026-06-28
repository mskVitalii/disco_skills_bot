import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.keyboards.inline import (
    back_keyboard,
    dialog_keyboard,
    empty_keyboard,
    skills_keyboard,
    enumeration_keyboard,
)
from app.bot.states import DialogState
from app.core.config import settings
from app.services.dialog_service import (
    get_or_create_user,
    handle_go_back,
    handle_skill_deep_dive,
    handle_user_message,
    reset_dialog,
    update_node_message_id,
)

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


def _is_allowed(telegram_id: int) -> bool:
    if not settings.ALLOWED_USER_IDS:
        return True
    return telegram_id in settings.ALLOWED_USER_IDS


async def _edit_or_send(cq: CallbackQuery, text: str, reply_markup=None) -> None:
    """Edit the current message; fall back to sending a new one."""
    try:
        await cq.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest:
        await cq.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)


# ─── enum:{index} ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("enum:"))
async def cb_enum(cq: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(cq.from_user.id):
        await cq.answer()
        return

    try:
        index = int(cq.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await cq.answer("Ошибка")
        return

    data = await state.get_data()
    items: list[str] = data.get("pending_enum", [])

    if index >= len(items):
        await cq.answer("Вариант недоступен")
        return

    chosen = items[index]

    try:
        await cq.message.edit_reply_markup(reply_markup=empty_keyboard())
    except Exception:
        pass

    await cq.answer()
    await cq.message.answer(f"<i>— {chosen}</i>", parse_mode="HTML")

    user = await get_or_create_user(
        telegram_id=cq.from_user.id,
        chat_id=cq.message.chat.id,
        username=cq.from_user.username,
        first_name=cq.from_user.first_name or "",
    )

    try:
        await cq.message.bot.send_chat_action(chat_id=cq.message.chat.id, action="typing")
    except Exception:
        pass
    thinking = await cq.message.answer("⏳")
    text, ai_result, new_node_id = await handle_user_message(
        user=user,
        user_message=chosen,
    )

    kb = dialog_keyboard(ai_result, new_node_id, show_back=True)
    try:
        await thinking.delete()
    except Exception:
        pass
    sent = await cq.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await update_node_message_id(new_node_id, sent.message_id)
    await state.set_state(DialogState.active)


# ─── choice:{node_id}:{index} ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("choice:"))
async def cb_choice(cq: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(cq.from_user.id):
        await cq.answer()
        return

    logger.info("callback choice user_id=%s data=%r", cq.from_user.id, cq.data)
    parts = cq.data.split(":")
    if len(parts) < 3:
        await cq.answer("Неверный формат")
        return

    option_index = int(parts[2])

    # Remove buttons from the current message (choice made)
    try:
        await cq.message.edit_reply_markup(reply_markup=empty_keyboard())
    except TelegramBadRequest:
        pass

    await cq.answer()

    # Retrieve node data from cache to get option text
    from app.services.dialog_service import _load_node_cache, get_redis
    redis = get_redis()
    node_id = int(parts[1])
    cache = await _load_node_cache(redis, node_id)
    options = (cache or {}).get("options", [])
    chosen_text = options[option_index] if option_index < len(options) else f"Вариант {option_index + 1}"

    user = await get_or_create_user(
        telegram_id=cq.from_user.id,
        chat_id=cq.message.chat.id,
        username=cq.from_user.username,
        first_name=cq.from_user.first_name or "",
    )

    await cq.message.answer(f"<i>— {chosen_text}</i>", parse_mode="HTML")

    try:
        await cq.message.bot.send_chat_action(chat_id=cq.message.chat.id, action="typing")
    except Exception:
        pass
    thinking = await cq.message.answer("⏳")
    text, ai_result, new_node_id = await handle_user_message(
        user=user,
        user_message=chosen_text,
    )

    kb = dialog_keyboard(ai_result, new_node_id, show_back=True)
    try:
        await thinking.delete()
    except Exception:
        pass
    sent = await cq.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await update_node_message_id(new_node_id, sent.message_id)
    await state.set_state(DialogState.active)


# ─── skill:{skill_name} ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("skill:"))
async def cb_skill(cq: CallbackQuery) -> None:
    if not _is_allowed(cq.from_user.id):
        await cq.answer()
        return

    skill_name = cq.data.split(":", 1)[1]
    logger.info("callback skill user_id=%s skill=%s", cq.from_user.id, skill_name)
    await cq.answer(f"Спрашиваю {skill_name}…")

    user = await get_or_create_user(
        telegram_id=cq.from_user.id,
        chat_id=cq.message.chat.id,
        username=cq.from_user.username,
        first_name=cq.from_user.first_name or "",
    )

    text = await handle_skill_deep_dive(user, skill_name)
    if text:
        await cq.message.answer(text, parse_mode="HTML", reply_markup=back_keyboard())
    else:
        await cq.message.answer("Характеристика молчит.", reply_markup=back_keyboard())


# ─── back ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "back")
async def cb_back(cq: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(cq.from_user.id):
        await cq.answer()
        return

    logger.info("callback back user_id=%s", cq.from_user.id)
    user = await get_or_create_user(
        telegram_id=cq.from_user.id,
        chat_id=cq.message.chat.id,
        username=cq.from_user.username,
        first_name=cq.from_user.first_name or "",
    )

    prev_cache = await handle_go_back(user)

    if not prev_cache:
        await cq.answer("Некуда возвращаться.")
        return

    await cq.answer("Возвращаюсь…")

    skill_names = prev_cache.get("skill_names", [])
    user_msg = prev_cache.get("user_message", "")

    text = f"◀ <i>Вернулись к:</i> <b>{user_msg[:80]}</b>"
    kb = skills_keyboard(skill_names)
    await cq.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await state.set_state(DialogState.active)


# ─── new ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "new")
async def cb_new(cq: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(cq.from_user.id):
        await cq.answer()
        return

    logger.info("callback new user_id=%s", cq.from_user.id)
    user = await get_or_create_user(
        telegram_id=cq.from_user.id,
        chat_id=cq.message.chat.id,
        username=cq.from_user.username,
        first_name=cq.from_user.first_name or "",
    )

    await reset_dialog(user)
    await cq.answer("Диалог сброшен.")

    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass

    await cq.message.answer(
        "Новый диалог начат. Напиши что-нибудь или используй /scene для сцены."
    )
    await state.set_state(DialogState.active)
