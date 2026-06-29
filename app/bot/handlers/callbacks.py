import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.keyboards.inline import (
    back_keyboard,
    skills_keyboard,
    enumeration_keyboard,
)
from app.bot.states import DialogState
from app.services.dialog_service import (
    get_or_create_user,
    handle_go_back,
    handle_skill_deep_dive,
    handle_user_message,
    perform_skill_check,
    reset_dialog,
    update_node_message_id,
)

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


async def _edit_or_send(cq: CallbackQuery, text: str, reply_markup=None) -> None:
    """Edit the current message; fall back to sending a new one."""
    try:
        await cq.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest:
        await cq.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)


# ─── enum:{index} ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("enum:"))
async def cb_enum(cq: CallbackQuery, state: FSMContext) -> None:
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
        await cq.message.edit_reply_markup(reply_markup=None)
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


# ─── roll:{node_id}:{skill_index} ────────────────────────────────────────────

@router.callback_query(F.data.startswith("roll:"))
async def cb_roll(cq: CallbackQuery) -> None:
    parts = cq.data.split(":")
    if len(parts) < 3:
        await cq.answer("Ошибка")
        return

    try:
        node_id = int(parts[1])
        skill_index = int(parts[2])
    except ValueError:
        await cq.answer("Ошибка")
        return

    from app.services.dialog_service import _load_node_cache, get_redis
    redis = get_redis()
    cache = await _load_node_cache(redis, node_id)
    if not cache:
        await cq.answer("Данные истекли.")
        return

    skill_names = cache.get("skill_names", [])
    checks = cache.get("checks", [])

    if skill_index >= len(skill_names) or skill_index >= len(checks):
        await cq.answer("Проверка недоступна.")
        return

    skill_name = skill_names[skill_index]
    check = checks[skill_index]

    if not check.get("has_check"):
        await cq.answer("Нет проверки.")
        return

    await cq.answer("Бросаю кубики…")

    # Remove the roll button after it's been used
    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    user = await get_or_create_user(
        telegram_id=cq.from_user.id,
        chat_id=cq.message.chat.id,
        username=cq.from_user.username,
        first_name=cq.from_user.first_name or "",
    )

    result_text = await perform_skill_check(user, skill_name, check)
    if result_text:
        await cq.message.answer(result_text, parse_mode="HTML")


# ─── skill:{skill_name} ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("skill:"))
async def cb_skill(cq: CallbackQuery) -> None:
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
