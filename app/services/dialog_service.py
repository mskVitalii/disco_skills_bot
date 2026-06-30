import asyncio
import json
import logging
from dataclasses import asdict

import redis.asyncio as aioredis

from app.core.database import get_redis
from app.data.skills import ALL_SKILLS
from app.models.dialog import Dialog, DialogNode
from app.models.stats import SkillInvocationStat, UserMajorIdea
from app.models.user import User, UserSkillLevel
from app.services.ai_service import (
    DialogAIResult,
    SkillResponse,
    extract_major_ideas,
    generate_embedding,
    generate_scene,
    generate_skill_deep_response,
    generate_skill_responses,
)
from app.services.skill_service import roll_check

logger = logging.getLogger(__name__)

DIALOG_STATE_TTL = 60 * 60 * 24  # 24 hours

_pgvector_available: bool | None = None  # None = not yet probed


async def _check_pgvector() -> bool:
    global _pgvector_available
    if _pgvector_available is not None:
        return _pgvector_available
    try:
        from tortoise import connections
        conn = connections.get("default")
        _, rows = await conn.execute_query(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        )
        _pgvector_available = bool(rows)
    except Exception:
        _pgvector_available = False
    if not _pgvector_available:
        logger.warning("[embed] pgvector extension not installed — embedding features disabled")
    return _pgvector_available


# ─── Redis helpers ────────────────────────────────────────────────────────────

def _state_key(user_id: int, chat_id: int) -> str:
    return f"dialog_state:{user_id}:{chat_id}"


def _node_key(node_id: int) -> str:
    return f"dialog_node:{node_id}"


async def _save_state(redis: aioredis.Redis, user_id: int, chat_id: int, state: dict) -> None:
    await redis.setex(_state_key(user_id, chat_id), DIALOG_STATE_TTL, json.dumps(state))


async def _load_state(redis: aioredis.Redis, user_id: int, chat_id: int) -> dict | None:
    raw = await redis.get(_state_key(user_id, chat_id))
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

    header = f"{skill.emoji} <i>{skill.name}</i>"
    return f"{header}\n{sr.text}"


async def perform_skill_check(user: User, skill_name: str, check: dict) -> str:
    """Roll dice for a deferred skill check and return the formatted result."""
    skill = ALL_SKILLS.get(skill_name)
    if not skill:
        return ""

    level = await get_skill_level(user, skill_name)
    difficulty = check.get("check_difficulty", 10)
    roll = roll_check(level, difficulty)
    logger.info(
        "[dialog] dice roll %s: d1=%d d2=%d level=%d total=%d vs %d → %s",
        skill_name, roll.die1, roll.die2, level, roll.total, difficulty,
        "SUCCESS" if roll.is_success else "FAIL",
    )

    roll_line = roll.format_html()
    extra = ""
    if roll.is_success and check.get("success_text"):
        extra = f"\n{check['success_text']}"
    elif not roll.is_success and check.get("failure_text"):
        extra = f"\n{check['failure_text']}"

    return f"{roll_line}{extra}"


async def build_response_message(
    user: User,
    ai_result: DialogAIResult,
) -> str:
    blocks = []
    for sr in ai_result.skill_responses:
        logger.info("[dialog] formatting skill: %s has_check=%s", sr.skill_name, sr.has_check)
        block = await format_skill_block(user, sr)
        if block:
            blocks.append(block)

    if not blocks:
        logger.warning("[dialog] no skill blocks produced — skill_responses=%d", len(ai_result.skill_responses))

    return "\n\n".join(blocks)


# ─── Statistics ──────────────────────────────────────────────────────────────

async def track_skill_invocations(user: User, skill_names: list[str]) -> None:
    for name in skill_names:
        stat, created = await SkillInvocationStat.get_or_create(
            user=user, skill_name=name, defaults={"count": 0}
        )
        if not created:
            await SkillInvocationStat.filter(id=stat.id).update(count=stat.count + 1)
        else:
            await SkillInvocationStat.filter(id=stat.id).update(count=1)


async def get_skill_stats(user: User) -> list[tuple[str, int]]:
    """Returns list of (skill_name, count) sorted by count descending."""
    stats = await SkillInvocationStat.filter(user=user).order_by("-count").all()
    return [(s.skill_name, s.count) for s in stats]


# ─── Major ideas ──────────────────────────────────────────────────────────────

async def _extract_and_save_ideas(user: User, conversation_snippet: str) -> None:
    try:
        existing = await UserMajorIdea.filter(user=user).order_by("-created_at").limit(10).all()
        existing_texts = [i.idea for i in existing]
        new_ideas = await extract_major_ideas(conversation_snippet, existing_texts)
        for idea in new_ideas:
            await UserMajorIdea.create(user=user, idea=idea)
            logger.info("[ideas] saved new idea for user=%s: %r", user.telegram_id, idea[:60])
    except Exception as e:
        logger.error("[ideas] extraction failed: %s", e)


async def get_user_ideas(user: User, limit: int = 5) -> list[str]:
    ideas = await UserMajorIdea.filter(user=user).order_by("-created_at").limit(limit).all()
    return [i.idea for i in ideas]


# ─── Semantic search (pgvector) ──────────────────────────────────────────────

async def _store_embedding(node_id: int, embedding: list[float]) -> None:
    if not await _check_pgvector():
        return
    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
    try:
        from tortoise import connections
        conn = connections.get("default")
        await conn.execute_query(
            "UPDATE dialog_nodes SET embedding = $1::vector WHERE id = $2",
            [vec_str, node_id],
        )
    except Exception as e:
        logger.error("[embed] store failed node_id=%s: %s", node_id, e)


async def semantic_search(
    user_telegram_id: int,
    chat_id: int,
    query_embedding: list[float],
    exclude_dialog_id: str | None = None,
    limit: int = 3,
) -> list[str]:
    """Find user messages from past dialogs in the same chat that are semantically similar."""
    if not await _check_pgvector():
        return []
    vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    try:
        from tortoise import connections
        conn = connections.get("default")
        exclude_clause = "AND d.id != $5::uuid" if exclude_dialog_id else ""
        params: list = [vec_str, user_telegram_id, chat_id, limit]
        if exclude_dialog_id:
            params.append(exclude_dialog_id)

        _, rows = await conn.execute_query(
            f"""SELECT dn.user_message,
                       1 - (dn.embedding <=> $1::vector) AS similarity
                FROM dialog_nodes dn
                JOIN dialogs d ON dn.dialog_id = d.id
                JOIN users u ON d.user_id = u.id
                WHERE u.telegram_id = $2
                  AND d.chat_id = $3
                  AND dn.embedding IS NOT NULL
                  {exclude_clause}
                ORDER BY dn.embedding <=> $1::vector
                LIMIT $4""",
            params,
        )
        # rows is a list of asyncpg Record objects
        results = []
        for row in rows:
            sim = float(row["similarity"])
            if sim >= 0.75:
                results.append(str(row["user_message"]))
        logger.info("[embed] semantic_search found %d similar msgs (threshold 0.75)", len(results))
        return results
    except Exception as e:
        logger.warning("[embed] semantic_search failed: %s", e)
        return []


async def _generate_and_store_embedding(node_id: int, text: str) -> None:
    embedding = await generate_embedding(text)
    if embedding:
        await _store_embedding(node_id, embedding)


# ─── Recent context loader ────────────────────────────────────────────────────

async def _get_dialog_context(dialog_id: str, exclude_last: bool = True) -> list[dict]:
    """Load last ~15 dialog nodes as chat messages for AI context."""
    nodes = await DialogNode.filter(dialog__id=dialog_id).order_by("-created_at").limit(16).all()
    nodes = list(reversed(nodes))
    if exclude_last and nodes:
        nodes = nodes[:-1]  # exclude current (not yet created)

    messages = []
    for node in nodes[-15:]:
        messages.append({"role": "user", "content": node.user_message})
        if node.skill_responses:
            parts = []
            for sr in node.skill_responses:
                if isinstance(sr, dict) and sr.get("text"):
                    parts.append(f"{sr.get('skill_name', '')}: {sr['text']}")
            if parts:
                messages.append({"role": "assistant", "content": "\n".join(parts)})
    return messages


# ─── Dialog orchestration ─────────────────────────────────────────────────────

async def handle_user_message(
    user: User,
    user_message: str,
    context_messages: list[dict] | None = None,
) -> tuple[str, DialogAIResult, int]:
    """Process a user message, return (formatted_text, ai_result, node_id)."""
    redis = get_redis()
    state = await _load_state(redis, user.telegram_id, user.chat_id)

    dialog_id = state.get("dialog_id") if state else None
    parent_node_id = state.get("current_node_id") if state else None

    # Get or create active dialog
    if dialog_id:
        dialog = await Dialog.get_or_none(id=dialog_id, is_active=True)
    else:
        dialog = None

    if not dialog:
        dialog = await Dialog.create(user=user, title=user_message[:100], chat_id=user.chat_id)
        dialog_id = str(dialog.id)

    # Load recent dialog messages and semantic search in parallel
    tasks = []
    if context_messages is None and dialog_id:
        tasks.append(_get_dialog_context(dialog_id))
    else:
        tasks.append(asyncio.sleep(0))  # placeholder

    tasks.append(get_user_ideas(user))
    tasks.append(generate_embedding(user_message))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    if context_messages is None:
        context_messages = results[0] if isinstance(results[0], list) else []
    user_ideas = results[1] if isinstance(results[1], list) else []
    query_embedding = results[2] if isinstance(results[2], list) else None

    # Semantic search in past dialogs of the same chat (outside current dialog)
    semantic_msgs: list[str] = []
    if query_embedding:
        semantic_msgs = await semantic_search(
            user_telegram_id=user.telegram_id,
            chat_id=user.chat_id,
            query_embedding=query_embedding,
            exclude_dialog_id=dialog_id,
        )

    logger.info("[dialog] generating response for user_id=%s msg=%r", user.telegram_id, user_message[:80])
    ai_result = await generate_skill_responses(
        user_message=user_message,
        context_messages=context_messages,
        user_ideas=user_ideas,
        semantic_context=semantic_msgs,
    )
    logger.info(
        "[dialog] ai_result: skills=%s",
        [sr.skill_name for sr in ai_result.skill_responses],
    )

    node = await DialogNode.create(
        dialog=dialog,
        user_message=user_message,
        skill_responses=[asdict(sr) for sr in ai_result.skill_responses],
        response_options=[],
        parent_id=parent_node_id,
    )

    text = await build_response_message(user, ai_result)

    history = (state or {}).get("history", [])
    if parent_node_id:
        history.append({"node_id": parent_node_id})
    history = history[-10:]

    new_state = {
        "dialog_id": str(dialog.id),
        "current_node_id": node.id,
        "history": history,
    }
    await _save_state(redis, user.telegram_id, user.chat_id, new_state)

    node_cache = {
        "user_message": user_message,
        "skill_names": [sr.skill_name for sr in ai_result.skill_responses],
        "parent_node_id": parent_node_id,
        "checks": [
            {
                "has_check": sr.has_check,
                "check_difficulty": sr.check_difficulty,
                "check_description": sr.check_description,
                "success_text": sr.success_text,
                "failure_text": sr.failure_text,
            }
            for sr in ai_result.skill_responses
        ],
    }
    await _save_node_cache(redis, node.id, node_cache)

    # Track skill invocation stats
    invoked = [sr.skill_name for sr in ai_result.skill_responses]
    if invoked:
        asyncio.create_task(track_skill_invocations(user, invoked))

    # Store embedding for this node (reuse already-fetched embedding or generate fresh)
    if query_embedding:
        asyncio.create_task(_store_embedding(node.id, query_embedding))
    else:
        asyncio.create_task(_generate_and_store_embedding(node.id, user_message))

    # Fire-and-forget: extract major ideas from conversation
    if context_messages:
        snippet = f"{user_message}\n" + "\n".join(
            m["content"] for m in context_messages[-6:] if m.get("role") == "user"
        )
        asyncio.create_task(_extract_and_save_ideas(user, snippet))

    return text, ai_result, node.id


async def handle_scene_command(
    user: User,
    description: str,
) -> tuple[str, DialogAIResult, int]:
    """Create a dialog from a scene description."""
    redis = get_redis()

    # End any existing active dialog
    existing_state = await _load_state(redis, user.telegram_id, user.chat_id)
    if existing_state and existing_state.get("dialog_id"):
        await Dialog.filter(id=existing_state["dialog_id"]).update(is_active=False)

    ai_result = await generate_scene(description)

    dialog = await Dialog.create(user=user, title=description[:100], chat_id=user.chat_id)
    node = await DialogNode.create(
        dialog=dialog,
        user_message=description,
        skill_responses=[asdict(sr) for sr in ai_result.skill_responses],
        response_options=[],
    )

    text = await build_response_message(user, ai_result)

    new_state = {
        "dialog_id": str(dialog.id),
        "current_node_id": node.id,
        "history": [],
    }
    await _save_state(redis, user.telegram_id, user.chat_id, new_state)
    await _save_node_cache(redis, node.id, {
        "user_message": description,
        "skill_names": [sr.skill_name for sr in ai_result.skill_responses],
        "parent_node_id": None,
        "checks": [
            {
                "has_check": sr.has_check,
                "check_difficulty": sr.check_difficulty,
                "check_description": sr.check_description,
                "success_text": sr.success_text,
                "failure_text": sr.failure_text,
            }
            for sr in ai_result.skill_responses
        ],
    })

    return text, ai_result, node.id


async def handle_skill_deep_dive(
    user: User,
    skill_name: str,
) -> str:
    redis = get_redis()
    state = await _load_state(redis, user.telegram_id, user.chat_id)
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
    state = await _load_state(redis, user.telegram_id, user.chat_id)
    if not state:
        return None

    history = state.get("history", [])
    if not history:
        return None

    prev = history.pop()
    prev_node_id = prev["node_id"]

    state["current_node_id"] = prev_node_id
    state["history"] = history
    await _save_state(redis, user.telegram_id, user.chat_id, state)

    return await _load_node_cache(redis, prev_node_id)


async def get_current_context_message(user: User) -> str:
    """Return the last user message from current dialog node, or empty string."""
    redis = get_redis()
    state = await _load_state(redis, user.telegram_id, user.chat_id)
    if not state:
        return ""
    node_id = state.get("current_node_id")
    if not node_id:
        return ""
    cache = await _load_node_cache(redis, node_id)
    return (cache or {}).get("user_message", "")


async def reset_dialog(user: User) -> None:
    redis = get_redis()
    state = await _load_state(redis, user.telegram_id, user.chat_id)
    if state and state.get("dialog_id"):
        await Dialog.filter(id=state["dialog_id"]).update(is_active=False)
    await redis.delete(_state_key(user.telegram_id, user.chat_id))


async def update_node_message_id(node_id: int, message_id: int) -> None:
    await DialogNode.filter(id=node_id).update(telegram_message_id=message_id)
    redis = get_redis()
    cache = await _load_node_cache(redis, node_id)
    if cache:
        cache["message_id"] = message_id
        await _save_node_cache(redis, node_id, cache)
