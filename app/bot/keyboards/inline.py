from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.data.skills import ALL_SKILLS
from app.services.ai_service import DialogAIResult

MAX_OPTION_LEN = 32  # Telegram button label limit (display)
MAX_CB_LEN = 64       # Telegram callback_data byte limit


def _truncate(text: str, max_len: int = MAX_OPTION_LEN) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def dialog_keyboard(
    ai_result: DialogAIResult,
    node_id: int,
    show_back: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    # Response option buttons (up to 3)
    for i, option in enumerate(ai_result.response_options[:3]):
        cb = f"choice:{node_id}:{i}"
        if len(cb.encode()) > MAX_CB_LEN:
            cb = f"ch:{node_id}:{i}"
        rows.append([
            InlineKeyboardButton(
                text=_truncate(option),
                callback_data=cb,
            )
        ])

    # Skill deep-dive buttons (one per responding skill)
    skill_buttons = []
    for sr in ai_result.skill_responses:
        skill = ALL_SKILLS.get(sr.skill_name)
        if not skill:
            continue
        # skill name is short enough: "skill:НАЗВАНИЕ" ≤ 64 bytes for our names
        cb = f"skill:{sr.skill_name}"
        skill_buttons.append(
            InlineKeyboardButton(
                text=f"{skill.emoji} {_truncate(skill.name, 16)}",
                callback_data=cb,
            )
        )
    if skill_buttons:
        # Pair them 2 per row
        for i in range(0, len(skill_buttons), 2):
            rows.append(skill_buttons[i : i + 2])

    # Navigation
    nav = []
    if show_back:
        nav.append(InlineKeyboardButton(text="◀ Назад", callback_data="back"))
    nav.append(InlineKeyboardButton(text="✦ Новый", callback_data="new"))
    rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def empty_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with only 'New dialog' button — used when editing old messages."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✦ Новый диалог", callback_data="new")]
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀ Назад", callback_data="back"),
                InlineKeyboardButton(text="✦ Новый", callback_data="new"),
            ]
        ]
    )


def skills_keyboard(skill_names: list[str]) -> InlineKeyboardMarkup:
    """Keyboard listing skills for a deep-dive after going back."""
    rows = []
    buttons = []
    for name in skill_names:
        skill = ALL_SKILLS.get(name)
        if not skill:
            continue
        buttons.append(
            InlineKeyboardButton(
                text=f"{skill.emoji} {_truncate(skill.name, 16)}",
                callback_data=f"skill:{name}",
            )
        )
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i : i + 2])
    rows.append([InlineKeyboardButton(text="✦ Новый", callback_data="new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
