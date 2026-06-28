import logging
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.data.skills import ALL_SKILLS, skill_list_for_prompt

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def get_openai() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


# ── Pydantic schemas for structured outputs ────────────────────────────────

class SkillResponseSchema(BaseModel):
    skill: str
    text: str
    dialog_option: str = ""   # what THIS skill suggests as next action/reply (shown on button)
    has_check: bool = False
    check_difficulty: int = 10
    check_description: str = ""
    success_text: str = ""
    failure_text: str = ""


class DialogAISchema(BaseModel):
    responses: list[SkillResponseSchema]


class SceneAISchema(BaseModel):
    title: str
    opening: str
    responses: list[SkillResponseSchema]


# ── Internal dataclasses returned to callers ───────────────────────────────

@dataclass
class SkillResponse:
    skill_name: str
    text: str
    dialog_option: str = ""
    has_check: bool = False
    check_difficulty: int = 10
    check_description: str = ""
    success_text: str = ""
    failure_text: str = ""


@dataclass
class DialogAIResult:
    skill_responses: list[SkillResponse] = field(default_factory=list)
    response_options: list[str] = field(default_factory=list)


# ── System prompts ─────────────────────────────────────────────────────────

_SYSTEM_GENERATE = """Ты — игра Disco Elysium в формате Telegram-бота.
Внутренние голоса-характеристики комментируют сообщение пользователя.

Правила:
- Выбери ТОЛЬКО 1 характеристику — ту, которой ДЕЙСТВИТЕЛЬНО есть что сказать. Не больше.
- Если ни одной характеристике нечего добавить — верни пустой список responses: []
- В поле skill указывай ТОЛЬКО название заглавными буквами, без эмодзи. Например: ЛОГИКА, ЭМПАТИЯ
- Голос говорит ровно 1 предложение — острое, точное, в своём стиле. Никаких вводных слов.
- Если у характеристики написано "матерится" — мат обязателен.
- dialog_option — короткая реплика или действие, макс 40 символов
- has_check: только если есть реальный интересный исход — конкретный факт, который может вскрыться, или действие, которое может не получиться. Без проверок на абстрактные «понять», «уловить», «осознать».
- check_description — конкретное действие на кнопке, глагол + объект (макс 40 символов). Например: "Вспомнить год постройки", "Угадать мотив"
- success_text — КОНКРЕТНЫЙ факт/деталь/реплика при успехе. Не "всплывает что-то" — а именно ЧТО всплыло
- failure_text — конкретная горькая ремарка при провале. Не "не получилось" — а что именно пошло не так

Список характеристик:
{skills_list}"""

_SYSTEM_SCENE = """Ты — мастер диалогов Disco Elysium.
По описанию сцены создай структурированный диалог.
Каждый голос указывает dialog_option — короткую реплику или действие для кнопки продолжения.

Список характеристик:
{skills_list}"""

_SYSTEM_SKILL_DEEP = """Ты — характеристика {skill_name} ({skill_emoji}) из Disco Elysium.
{system_prompt}

Пользователь хочет услышать твоё углублённое мнение.
Дай развёрнутый ответ (3–5 предложений) в своём стиле.
Если уместно — предложи конкретное действие или провокационный вопрос."""

_SYSTEM_EXTRACT_IDEAS = """Ты анализируешь переписку и выявляешь магистральные идеи собеседника.
Верни JSON: {"ideas": ["идея 1", "идея 2"]} — 0–2 ключевые темы/паттерны/ценности.
Каждая идея — ёмкая фраза до 80 символов. Только если идея устойчивая и существенная.
Если ничего нового — {"ideas": []}."""


# ── Public API ─────────────────────────────────────────────────────────────

async def generate_skill_responses(
    user_message: str,
    context_messages: list[dict] | None = None,
    user_ideas: list[str] | None = None,
    semantic_context: list[str] | None = None,
) -> DialogAIResult:
    skills_list = skill_list_for_prompt()

    messages: list[dict] = [
        {
            "role": "system",
            "content": _SYSTEM_GENERATE.format(skills_list=skills_list),
        }
    ]

    # Inject user profile as a second system message
    if user_ideas:
        ideas_text = "\n".join(f"- {idea}" for idea in user_ideas)
        messages.append({
            "role": "system",
            "content": f"Образ пользователя (магистральные идеи):\n{ideas_text}",
        })

    # Inject semantically similar past messages as additional context
    if semantic_context:
        similar_text = "\n".join(f"- {m}" for m in semantic_context)
        messages.append({
            "role": "system",
            "content": f"Похожие темы из прошлых разговоров:\n{similar_text}",
        })

    if context_messages:
        messages.extend(context_messages[-14:])

    messages.append({"role": "user", "content": user_message})

    logger.info("[AI→] user: %r", user_message)
    try:
        response = await get_openai().beta.chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=messages,
            response_format=DialogAISchema,
            temperature=0.9,
            max_completion_tokens=900,
        )
        parsed: DialogAISchema = response.choices[0].message.parsed
        for r in parsed.responses:
            logger.info("[AI←] %s | %r | option: %r", r.skill, r.text[:60], r.dialog_option)
        return _from_dialog_schema(parsed)
    except Exception as e:
        logger.error("OpenAI generate_skill_responses error: %s", e)
        return DialogAIResult()


async def generate_scene(description: str) -> DialogAIResult:
    skills_list = skill_list_for_prompt()
    try:
        response = await get_openai().beta.chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": _SYSTEM_SCENE.format(skills_list=skills_list),
                },
                {"role": "user", "content": description},
            ],
            response_format=SceneAISchema,
            temperature=0.9,
            max_completion_tokens=900,
        )
        parsed: SceneAISchema = response.choices[0].message.parsed
        logger.info(
            "[AI] scene skills returned: %s",
            [(r.skill, repr(r.dialog_option[:30])) for r in parsed.responses],
        )
        result = _from_dialog_schema(parsed)
        if parsed.opening and result.skill_responses:
            result.skill_responses[0].text = f"<i>{parsed.opening}</i>\n\n" + result.skill_responses[0].text
        return result
    except Exception as e:
        logger.error("OpenAI generate_scene error: %s", e)
        return DialogAIResult()


async def generate_skill_deep_response(
    skill_name: str,
    user_message: str,
    context: str = "",
) -> str:
    skill = ALL_SKILLS.get(skill_name)
    if not skill:
        return ""

    system = _SYSTEM_SKILL_DEEP.format(
        skill_name=skill.name,
        skill_emoji=skill.emoji,
        system_prompt=skill.system_prompt,
    )
    user_content = f"Контекст разговора: {context}\n\nСообщение: {user_message}" if context else user_message

    try:
        response = await get_openai().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0.95,
            max_completion_tokens=400,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error("OpenAI generate_skill_deep_response error: %s", e)
        return ""


async def extract_major_ideas(
    conversation_text: str,
    existing_ideas: list[str] | None = None,
) -> list[str]:
    """Extract key themes/ideas from conversation. Returns list of idea strings."""
    context = ""
    if existing_ideas:
        context = f"Уже известные идеи:\n" + "\n".join(f"- {i}" for i in existing_ideas) + "\n\n"

    try:
        response = await get_openai().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_EXTRACT_IDEAS},
                {"role": "user", "content": f"{context}Переписка:\n{conversation_text}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_completion_tokens=200,
        )
        import json
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return [str(i) for i in data.get("ideas", [])]
    except Exception as e:
        logger.error("OpenAI extract_major_ideas error: %s", e)
        return []


async def generate_embedding(text: str) -> list[float] | None:
    """Generate a 1536-dim embedding for semantic search. Returns None on failure."""
    try:
        response = await get_openai().embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error("OpenAI embedding error: %s", e)
        return None


async def transcribe_voice(file_bytes: bytes, filename: str = "voice.ogg") -> str:
    import io
    try:
        response = await get_openai().audio.transcriptions.create(
            model=settings.WHISPER_MODEL,
            file=(filename, io.BytesIO(file_bytes), "audio/ogg"),
            language="ru",
        )
        return response.text
    except Exception as e:
        logger.error("Whisper transcription error: %s", e)
        return ""


# ── Helpers ────────────────────────────────────────────────────────────────

def _normalize_skill_name(raw: str) -> str:
    """AI sometimes returns '⚧️ АНДРОГИННОСТЬ' instead of 'АНДРОГИННОСТЬ' — strip emoji prefix."""
    name = raw.strip()
    if name in ALL_SKILLS:
        return name
    # Try dropping the first token (emoji) if it's not a known skill by itself
    parts = name.split(None, 1)
    if len(parts) == 2 and parts[1] in ALL_SKILLS:
        return parts[1]
    return name


def _from_dialog_schema(data: DialogAISchema | SceneAISchema) -> DialogAIResult:
    responses = []
    options = []
    for r in data.responses:
        skill_name = _normalize_skill_name(r.skill)
        if skill_name not in ALL_SKILLS:
            logger.warning("[AI] unknown skill filtered: %r (normalized: %r)", r.skill, skill_name)
            continue
        logger.info("[AI] skill accepted: %s | option: %r", skill_name, r.dialog_option)
        responses.append(
            SkillResponse(
                skill_name=skill_name,
                text=r.text,
                dialog_option=r.dialog_option,
                has_check=r.has_check,
                check_difficulty=r.check_difficulty,
                check_description=r.check_description,
                success_text=r.success_text,
                failure_text=r.failure_text,
            )
        )
        if r.dialog_option:
            options.append(r.dialog_option)

    logger.info("[AI] final: %d skills, %d options", len(responses), len(options))
    return DialogAIResult(skill_responses=responses, response_options=options)
