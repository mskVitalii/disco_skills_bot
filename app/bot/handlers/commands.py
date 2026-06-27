import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.states import DialogState
from app.core.config import settings
from app.data.skills import ALL_SKILLS, CATEGORIES
from app.models.user import User, UserSkillLevel
from app.services.dialog_service import (
    get_or_create_user,
    handle_scene_command,
    reset_dialog,
)
from app.bot.keyboards.inline import dialog_keyboard

logger = logging.getLogger(__name__)
router = Router(name="commands")


def _is_allowed(telegram_id: int) -> bool:
    if not settings.ALLOWED_USER_IDS:
        return True
    return telegram_id in settings.ALLOWED_USER_IDS


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return

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
        "Я — голоса внутри. Напиши что-нибудь — и мы прокомментируем.\n\n"
        "<b>Команды:</b>\n"
        "/scene <i>описание</i> — создать сцену для игры\n"
        "/skills — текущие уровни характеристик\n"
        "/new — сбросить текущий диалог",
        parse_mode="HTML",
    )


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return

    user = await User.get_or_none(telegram_id=message.from_user.id)
    if user:
        await reset_dialog(user)

    await state.set_state(DialogState.active)
    await message.answer("Диалог сброшен. Начинаем заново.")


@router.message(Command("scene"))
async def cmd_scene(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return

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
    if not _is_allowed(message.from_user.id):
        return

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


@router.message(Command("skills"))
async def cmd_skills(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return

    user = await User.get_or_none(telegram_id=message.from_user.id)
    if not user:
        await message.answer("Сначала отправь /start")
        return

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
