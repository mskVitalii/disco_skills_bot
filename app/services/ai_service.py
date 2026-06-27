import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings
from app.data.skills import ALL_SKILLS, skill_list_for_prompt

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def get_openai() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


@dataclass
class SkillResponse:
    skill_name: str
    text: str
    has_check: bool = False
    check_difficulty: int = 10
    check_description: str = ""
    success_text: str = ""
    failure_text: str = ""


@dataclass
class DialogAIResult:
    skill_responses: list[SkillResponse] = field(default_factory=list)
    response_options: list[str] = field(default_factory=list)


_SYSTEM_GENERATE = """Ты — игра Disco Elysium в формате Telegram-бота.
Несколько характеристик (голосов) комментируют сообщение пользователя.
Каждый голос говорит кратко (1–3 предложения), в своём стиле.

Правила:
- Выбери 2–{max_responses} наиболее подходящих характеристики из списка
- Для каждой напиши ответ в характерном стиле
- Если уместно — добавь активную проверку (has_check=true): что попробовать и какой difficulty
- Придумай 3 варианта ответа для кнопок (response_options): что пользователь может ответить/сделать

Список характеристик:
{skills_list}

Отвечай строго JSON (без markdown):
{{
  "responses": [
    {{
      "skill": "НАЗВАНИЕ",
      "text": "Текст от лица характеристики",
      "has_check": false,
      "check_difficulty": 10,
      "check_description": "Попробовать ...",
      "success_text": "При успехе: ...",
      "failure_text": "При провале: ..."
    }}
  ],
  "response_options": ["Вариант 1", "Вариант 2", "Вариант 3"]
}}"""

_SYSTEM_SCENE = """Ты — мастер диалогов Disco Elysium.
По описанию сцены создай структурированный диалог.

Формат ответа (строго JSON):
{{
  "title": "Короткое название сцены",
  "opening": "Вводный текст сцены (1–2 предложения)",
  "responses": [
    {{
      "skill": "ХАРАКТЕРИСТИКА",
      "text": "Реакция характеристики",
      "has_check": false,
      "check_difficulty": 10,
      "check_description": "...",
      "success_text": "...",
      "failure_text": "..."
    }}
  ],
  "response_options": ["Вариант 1", "Вариант 2", "Вариант 3"]
}}

Список характеристик:
{skills_list}"""

_SYSTEM_SKILL_DEEP = """Ты — характеристика {skill_name} ({skill_emoji}) из Disco Elysium.
{system_prompt}

Пользователь хочет услышать твоё углублённое мнение.
Дай развёрнутый ответ (3–5 предложений) в своём стиле.
Если уместно — предложи конкретное действие или провокационный вопрос."""


async def generate_skill_responses(
    user_message: str,
    context_messages: list[dict] | None = None,
    max_responses: int | None = None,
) -> DialogAIResult:
    max_r = max_responses or settings.MAX_SKILL_RESPONSES
    skills_list = skill_list_for_prompt()

    messages: list[dict] = [
        {
            "role": "system",
            "content": _SYSTEM_GENERATE.format(
                max_responses=max_r,
                skills_list=skills_list,
            ),
        }
    ]

    if context_messages:
        messages.extend(context_messages[-6:])  # last 3 exchanges

    messages.append({"role": "user", "content": user_message})

    try:
        response = await get_openai().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.9,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        return _parse_ai_result(data)
    except Exception as e:
        logger.error("OpenAI generate_skill_responses error: %s", e)
        return DialogAIResult()


async def generate_scene(description: str) -> DialogAIResult:
    skills_list = skill_list_for_prompt()
    try:
        response = await get_openai().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": _SYSTEM_SCENE.format(skills_list=skills_list),
                },
                {"role": "user", "content": description},
            ],
            response_format={"type": "json_object"},
            temperature=0.9,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        result = _parse_ai_result(data)
        # Attach title/opening to first response text if present
        title = data.get("title", "")
        opening = data.get("opening", "")
        if opening and result.skill_responses:
            result.skill_responses[0].text = f"<i>{opening}</i>\n\n" + result.skill_responses[0].text
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
            max_tokens=400,
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


def _parse_ai_result(data: dict) -> DialogAIResult:
    responses = []
    for r in data.get("responses", []):
        skill_name = r.get("skill", "")
        if skill_name not in ALL_SKILLS:
            continue
        responses.append(
            SkillResponse(
                skill_name=skill_name,
                text=r.get("text", ""),
                has_check=r.get("has_check", False),
                check_difficulty=int(r.get("check_difficulty", 10)),
                check_description=r.get("check_description", ""),
                success_text=r.get("success_text", ""),
                failure_text=r.get("failure_text", ""),
            )
        )
    options = [str(o) for o in data.get("response_options", [])[:3]]
    return DialogAIResult(skill_responses=responses, response_options=options)
