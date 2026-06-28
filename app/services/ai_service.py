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
Несколько характеристик (внутренних голосов) реагируют на сообщение пользователя.

Правила:
- Выбери 1–2 наиболее подходящих характеристики. Только те, которым есть что сказать по существу.
- В поле skill указывай ТОЛЬКО название характеристики заглавными буквами, без эмодзи. Например: АНДРОГИННОСТЬ, ЛОГИКА, ЭМПАТИЯ
- Каждый голос говорит ровно 1 предложение — острое, точное, строго в стиле из описания. Не больше. Только если есть что сказать.
- Если у характеристики в описании написано "матерится" — мат обязателен, не опционален.
- dialog_option — короткая реплика или действие от имени этой характеристики, макс 40 символов
- Если очень уместно — добавь проверку (has_check=true), но не злоупотребляй

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


# ── Public API ─────────────────────────────────────────────────────────────

async def generate_skill_responses(
    user_message: str,
    context_messages: list[dict] | None = None,
) -> DialogAIResult:
    skills_list = skill_list_for_prompt()

    messages: list[dict] = [
        {
            "role": "system",
            "content": _SYSTEM_GENERATE.format(skills_list=skills_list),
        }
    ]

    if context_messages:
        messages.extend(context_messages[-6:])

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
