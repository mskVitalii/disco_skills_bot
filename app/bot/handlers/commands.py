import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.states import DialogState
from app.data.skills import ALL_SKILLS, CATEGORIES, SKILL_NAMES
from app.models.user import User, UserSkillLevel
from app.services.dialog_service import (
    get_or_create_user,
    get_current_context_message,
    get_skill_stats,
    get_user_ideas,
    handle_scene_command,
    handle_user_message,
    reset_dialog,
    update_node_message_id,
)
from app.bot.keyboards.inline import dialog_keyboard

logger = logging.getLogger(__name__)
router = Router(name="commands")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:

    logger.info("/start user_id=%s username=%s", message.from_user.id, message.from_user.username)

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name or "",
    )

    await state.set_state(DialogState.active)

    name = message.from_user.first_name or "детектив"
    await message.answer(
        f"Добро пожаловать, {name}.\n\n"
        "Я — характеристики детектива. Напиши что-нибудь — и одна из нас прокомментирует.\n\n"
        "<b>Команды:</b>\n"
        "/disco — позвать характеристики прямо сейчас\n"
        "/scene <i>описание</i> — создать сцену для игры\n"
        "/skills — текущие уровни характеристик\n"
        "/stats — статистика характеристик и магистральные идеи\n"
        "/new — сбросить текущий диалог",
        parse_mode="HTML",
    )


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext) -> None:

    logger.info("/new user_id=%s", message.from_user.id)

    user = await User.get_or_none(telegram_id=message.from_user.id)
    if user:
        await reset_dialog(user)

    await state.set_state(DialogState.active)
    await message.answer("Диалог сброшен. Начинаем заново.")


@router.message(Command("scene"))
async def cmd_scene(message: Message, state: FSMContext) -> None:

    logger.info("/scene user_id=%s text=%r", message.from_user.id, message.text)

    # Extract description after /scene
    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await state.set_state(DialogState.waiting_scene)
        await message.answer(
            "Опиши сцену — и я создам диалог по ней.\n"
            "<i>Например: «Друг рассказывает о разрыве с партнёром»</i>",
            parse_mode="HTML",
        )
        return

    description = parts[1].strip()
    await _process_scene(message, state, description)


@router.message(DialogState.waiting_scene)
async def scene_description_received(message: Message, state: FSMContext) -> None:


    description = (message.text or "").strip()
    if not description:
        return

    await _process_scene(message, state, description)


async def _process_scene(message: Message, state: FSMContext, description: str) -> None:
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name or "",
    )

    thinking = await message.answer("⏳ Создаю сцену...")

    from app.services.dialog_service import handle_scene_command, update_node_message_id

    text, ai_result, node_id = await handle_scene_command(user, description)

    from app.bot.keyboards.inline import dialog_keyboard

    kb = dialog_keyboard(ai_result, node_id, show_back=False)

    await thinking.delete()
    sent = await message.answer(text, parse_mode="HTML", reply_markup=kb)
    await update_node_message_id(node_id, sent.message_id)

    await state.set_state(DialogState.active)


@router.message(Command("disco"))
async def cmd_disco(message: Message, state: FSMContext) -> None:

    logger.info("/disco user_id=%s text=%r", message.from_user.id, message.text)

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name or "",
    )

    # /disco НАЗВАНИЕ — детерминированный вызов конкретной характеристики
    text_parts = (message.text or "").split(maxsplit=1)
    skill_arg = text_parts[1].strip().upper() if len(text_parts) > 1 else ""
    forced_skill = skill_arg if skill_arg in ALL_SKILLS else None

    last_message = await get_current_context_message(user)
    if forced_skill:
        prompt = last_message or "Детектив молчит. Тишина."
    elif last_message:
        prompt = f"Мысли возвращаются к: «{last_message[:120]}»"
    else:
        prompt = "Детектив молчит. Тишина."

    text, ai_result, node_id = await handle_user_message(
        user=user, user_message=prompt, forced_skill=forced_skill
    )

    if not ai_result.skill_responses:
        return

    kb = dialog_keyboard(ai_result, node_id, show_back=bool(last_message))
    sent = await message.answer(text, parse_mode="HTML", reply_markup=kb)
    await update_node_message_id(node_id, sent.message_id)
    await state.set_state(DialogState.active)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:

    logger.info("/stats user_id=%s", message.from_user.id)

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name or "",
    )

    stats = await get_skill_stats(user)
    ideas = await get_user_ideas(user, limit=10)

    if not stats:
        await message.answer("Характеристики пока молчали — статистики нет.")
        return

    lines = ["<b>📊 Статистика вызовов:</b>\n"]
    total = sum(c for _, c in stats)
    for skill_name, count in stats[:15]:
        skill = ALL_SKILLS.get(skill_name)
        emoji = skill.emoji if skill else "•"
        pct = int(count / total * 100) if total else 0
        bar = "█" * min(pct // 5, 20)
        lines.append(f"{emoji} {skill_name}: {bar} {count} ({pct}%)")

    if ideas:
        lines.append("\n<b>💡 Магистральные идеи:</b>")
        for idea in ideas:
            lines.append(f"• {idea}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("skills"))
async def cmd_skills(message: Message) -> None:

    logger.info("/skills user_id=%s", message.from_user.id)

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name or "",
    )

    levels = await UserSkillLevel.filter(user=user).all()
    level_map = {l.skill_name: l.level for l in levels}

    lines = ["<b>Твои характеристики:</b>\n"]
    for category, names in CATEGORIES.items():
        lines.append(f"\n<b>{category}</b>")
        for name in names:
            skill = ALL_SKILLS[name]
            lvl = level_map.get(name, skill.default_level)
            bar = "█" * lvl + "░" * (10 - lvl)
            lines.append(f"{skill.emoji} {name}: {bar} {lvl}/10")

    await message.answer("\n".join(lines), parse_mode="HTML")
