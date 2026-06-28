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

    for i, sr in enumerate(ai_result.skill_responses):
        if not sr.dialog_option:
            continue
        skill = ALL_SKILLS.get(sr.skill_name)
        emoji = skill.emoji if skill else ""
        cb = f"choice:{node_id}:{i}"
        label = f"{emoji} {_truncate(sr.dialog_option, 36)}"
        rows.append([InlineKeyboardButton(text=label, callback_data=cb)])

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


def enumeration_keyboard(items: list[str]) -> InlineKeyboardMarkup:
    """Keyboard built from a user-enumerated list — each item becomes a choice button."""
    rows: list[list[InlineKeyboardButton]] = []
    for i, item in enumerate(items[:5]):
        rows.append([InlineKeyboardButton(
            text=_truncate(item, 40),
            callback_data=f"enum:{i}",
        )])
    rows.append([InlineKeyboardButton(text="✦ Новый", callback_data="new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
