import json
import logging
from dataclasses import asdict

import redis.asyncio as aioredis

from app.core.database import get_redis
from app.data.skills import ALL_SKILLS
from app.models.dialog import Dialog, DialogNode
from app.models.user import User, UserSkillLevel
from app.services.ai_service import (
    DialogAIResult,
    SkillResponse,
    generate_scene,
    generate_skill_deep_response,
    generate_skill_responses,
)
from app.services.skill_service import roll_check

logger = logging.getLogger(__name__)

DIALOG_STATE_TTL = 60 * 60 * 24  # 24 hours


# ─── Redis helpers ────────────────────────────────────────────────────────────

def _state_key(user_id: int) -> str:
    return f"dialog_state:{user_id}"


def _node_key(node_id: int) -> str:
    return f"dialog_node:{node_id}"


async def _save_state(redis: aioredis.Redis, user_id: int, state: dict) -> None:
    await redis.setex(_state_key(user_id), DIALOG_STATE_TTL, json.dumps(state))


async def _load_state(redis: aioredis.Redis, user_id: int) -> dict | None:
    raw = await redis.get(_state_key(user_id))
    return json.loads(raw) if raw else None


async def _save_node_cache(redis: aioredis.Redis, node_id: int, data: dict) -> None:
    await redis.setex(_node_key(node_id), DIALOG_STATE_TTL, json.dumps(data))


async def _load_node_cache(redis: aioredis.Redis, node_id: int) -> dict | None:
    raw = await redis.get(_node_key(node_id))
    return json.loads(raw) if raw else None


# ─── User helpers ─────────────────────────────────────────────────────────────

async def get_or_create_user(
    telegram_id: int,
    chat_id: int,
    username: str | None = None,
    first_name: str = "",
) -> User:
    user, created = await User.get_or_create(
        telegram_id=telegram_id,
        defaults={"chat_id": chat_id, "username": username, "first_name": first_name},
    )
    if not created:
        user.chat_id = chat_id
        if username is not None:
            user.username = username
        await user.save()
    return user


async def get_skill_level(user: User, skill_name: str) -> int:
    skill_def = ALL_SKILLS.get(skill_name)
    default = skill_def.default_level if skill_def else 3
    level, _ = await UserSkillLevel.get_or_create(
        user=user,
        skill_name=skill_name,
        defaults={"level": default},
    )
    return level.level


# ─── Message formatting ───────────────────────────────────────────────────────

async def format_skill_block(
    user: User,
    sr: SkillResponse,
) -> str:
    skill = ALL_SKILLS.get(sr.skill_name)
    if not skill:
        return ""

    header = f"{skill.emoji} <b><i>{skill.name}</i></b>"
    body = sr.text

    if not sr.has_check:
        return f"{header}\n{body}"

    level = await get_skill_level(user, sr.skill_name)
    roll = roll_check(level, sr.check_difficulty)

    check_line = ""
    if sr.check_description:
        check_line = f"\n<i>{sr.check_description}</i>\n"

    roll_line = roll.format_html()

    extra = ""
    if roll.is_success and sr.success_text:
        extra = f"\n{sr.success_text}"
    elif not roll.is_success and sr.failure_text:
        extra = f"\n{sr.failure_text}"

    return f"{header}\n{body}{check_line}\n{roll_line}{extra}"


async def build_response_message(
    user: User,
    ai_result: DialogAIResult,
) -> str:
    blocks = []
    for sr in ai_result.skill_responses:
        block = await format_skill_block(user, sr)
        if block:
            blocks.append(block)

    return "\n\n──────────\n\n".join(blocks) if blocks else "..."


# ─── Dialog orchestration ─────────────────────────────────────────────────────

async def handle_user_message(
    user: User,
    user_message: str,
    context_messages: list[dict] | None = None,
) -> tuple[str, DialogAIResult, int]:
    """Process a user message, return (formatted_text, ai_result, node_id)."""
    redis = get_redis()
    state = await _load_state(redis, user.telegram_id)

    dialog_id = state.get("dialog_id") if state else None
    parent_node_id = state.get("current_node_id") if state else None

    # Get or create active dialog
    if dialog_id:
        dialog = await Dialog.get_or_none(id=dialog_id, is_active=True)
    else:
        dialog = None

    if not dialog:
        dialog = await Dialog.create(user=user, title=user_message[:100])

    ai_result = await generate_skill_responses(
        user_message=user_message,
        context_messages=context_messages,
    )

    node = await DialogNode.create(
        dialog=dialog,
        user_message=user_message,
        skill_responses=[asdict(sr) for sr in ai_result.skill_responses],
        response_options=ai_result.response_options,
        parent_id=parent_node_id,
    )

    # Build the response text (with dice rolls baked in)
    text = await build_response_message(user, ai_result)

    history = (state or {}).get("history", [])
    if parent_node_id:
        history.append({"node_id": parent_node_id})
    history = history[-10:]  # keep last 10 nodes

    new_state = {
        "dialog_id": str(dialog.id),
        "current_node_id": node.id,
        "history": history,
    }
    await _save_state(redis, user.telegram_id, new_state)

    node_cache = {
        "user_message": user_message,
        "options": ai_result.response_options,
        "skill_names": [sr.skill_name for sr in ai_result.skill_responses],
        "parent_node_id": parent_node_id,
    }
    await _save_node_cache(redis, node.id, node_cache)

    return text, ai_result, node.id


async def handle_scene_command(
    user: User,
    description: str,
) -> tuple[str, DialogAIResult, int]:
    """Create a dialog from a scene description."""
    redis = get_redis()

    # End any existing active dialog
    existing_state = await _load_state(redis, user.telegram_id)
    if existing_state and existing_state.get("dialog_id"):
        await Dialog.filter(id=existing_state["dialog_id"]).update(is_active=False)

    ai_result = await generate_scene(description)

    dialog = await Dialog.create(user=user, title=description[:100])
    node = await DialogNode.create(
        dialog=dialog,
        user_message=description,
        skill_responses=[asdict(sr) for sr in ai_result.skill_responses],
        response_options=ai_result.response_options,
    )

    text = await build_response_message(user, ai_result)

    new_state = {
        "dialog_id": str(dialog.id),
        "current_node_id": node.id,
        "history": [],
    }
    await _save_state(redis, user.telegram_id, new_state)
    await _save_node_cache(redis, node.id, {
        "user_message": description,
        "options": ai_result.response_options,
        "skill_names": [sr.skill_name for sr in ai_result.skill_responses],
        "parent_node_id": None,
    })

    return text, ai_result, node.id


async def handle_skill_deep_dive(
    user: User,
    skill_name: str,
) -> str:
    redis = get_redis()
    state = await _load_state(redis, user.telegram_id)
    node_id = state.get("current_node_id") if state else None

    user_message = ""
    if node_id:
        node_cache = await _load_node_cache(redis, node_id)
        user_message = (node_cache or {}).get("user_message", "")

    text = await generate_skill_deep_response(skill_name, user_message)
    skill = ALL_SKILLS.get(skill_name)
    if skill and text:
        return f"{skill.emoji} <b><i>{skill.name}</i></b> (углублённо)\n\n{text}"
    return text


async def handle_go_back(user: User) -> dict | None:
    """Go back to previous node. Returns node cache dict or None."""
    redis = get_redis()
    state = await _load_state(redis, user.telegram_id)
    if not state:
        return None

    history = state.get("history", [])
    if not history:
        return None

    prev = history.pop()
    prev_node_id = prev["node_id"]

    state["current_node_id"] = prev_node_id
    state["history"] = history
    await _save_state(redis, user.telegram_id, state)

    return await _load_node_cache(redis, prev_node_id)


async def reset_dialog(user: User) -> None:
    redis = get_redis()
    state = await _load_state(redis, user.telegram_id)
    if state and state.get("dialog_id"):
        await Dialog.filter(id=state["dialog_id"]).update(is_active=False)
    await redis.delete(_state_key(user.telegram_id))


async def update_node_message_id(node_id: int, message_id: int) -> None:
    await DialogNode.filter(id=node_id).update(telegram_message_id=message_id)
    redis = get_redis()
    cache = await _load_node_cache(redis, node_id)
    if cache:
        cache["message_id"] = message_id
        await _save_node_cache(redis, node_id, cache)
