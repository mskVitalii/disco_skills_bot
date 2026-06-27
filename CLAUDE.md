# Disco Skills Bot — CLAUDE.md

Telegram-бот в стиле Disco Elysium: характеристики-голоса комментируют переписку,
бросают кубики и ведут диалог.

## Архитектура

```
main.py              — FastAPI app + aiogram lifespan (webhook/polling)
app/
  core/
    config.py        — pydantic-settings, все env vars
    database.py      — Tortoise ORM init + Redis client
  models/
    user.py          — User, UserSkillLevel
    dialog.py        — Dialog, DialogNode
  data/
    skills.py        — Все характеристики: эмодзи, промпт, категория, уровень
  services/
    ai_service.py    — OpenAI: выбор скиллов + генерация ответов + транскрипт
    skill_service.py — Механика кубиков (2d6 + уровень vs сложность)
    dialog_service.py— Оркестрация: получить/создать узел диалога, состояние в Redis
  bot/
    router.py        — Главный aiogram Router
    states.py        — FSM states (DialogState)
    handlers/
      commands.py    — /start, /scene, /skills
      messages.py    — Текст, голос, видео-кружки → dialog_service
      callbacks.py   — Инлайн-кнопки: выбор ответа, углубление в скилл, назад
    keyboards/
      inline.py      — Построители InlineKeyboardMarkup
docs/
  dev/SPEC_1.md      — Первая спецификация
  references/        — Оригинальные скиллы DE + наши характеристики
```

## Технологии

| Роль | Инструмент |
|------|-----------|
| Telegram | aiogram 3.x (webhook в prod, polling в dev) |
| HTTP сервер | FastAPI + uvicorn |
| База данных | PostgreSQL + Tortoise ORM |
| Миграции | aerich |
| Состояние диалога | Redis (aiogram FSMStorage + ручные ключи) |
| LLM | OpenAI gpt-4o-mini (структурированный вывод) |
| Транскрипт голоса | OpenAI Whisper |

## Переменные окружения

Все в `.env.example`. Ключевые:
- `BOT_TOKEN` — токен бота
- `WEBHOOK_URL` — URL для webhook (пусто = polling)
- `DATABASE_URL` — PostgreSQL DSN
- `REDIS_URL` — Redis URL
- `OPENAI_API_KEY` — ключ OpenAI
- `ALLOWED_USER_IDS` — через запятую, кому разрешён доступ

## Механика игры

### Проверка навыка (Skill Check)
```
Roll 2d6 + skill_level vs difficulty

Дубль 1 (⚀⚀) → КРИТИЧЕСКИЙ ПРОВАЛ (всегда)
Дубль 6 (⚅⚅) → КРИТИЧЕСКИЙ УСПЕХ (всегда)
сумма >= сложность → УСПЕХ
сумма < сложность  → ПРОВАЛ
```

| Сложность | Очки |
|-----------|------|
| Тривиальная | 6–7 |
| Лёгкая | 8–9 |
| Средняя | 10–11 |
| Сложная | 12 |
| Грозная | 13 |
| Легендарная | 14 |
| Героическая | 15 |
| Божественная | 16–17 |
| Невозможная | 18–20 |

### Формат сообщения характеристики
```
{emoji} <b><i>{НАЗВАНИЕ}</i></b>
{текст ответа}

🎲 [{d1}+{d2}] + {уровень} = {итого} vs {сложность} — <b>{РЕЗУЛЬТАТ}</b>
{текст при успехе/провале}
```

### Состояние диалога в Redis
```
dialog_state:{user_id}  →  JSON {
  dialog_id, current_node_id,
  history: [{node_id, message_id}]
}
dialog_node:{node_id}   →  JSON {
  user_message, responses, options,
  parent_node_id, message_id
}
```

### Callback data формат (≤ 64 байта)
```
choice:{index}       — выбрать вариант ответа
skill:{name}         — углубиться в конкретный скилл
back                 — вернуться к предыдущему узлу
new                  — начать новый диалог
scene:{short_id}     — перейти к заранее созданной сцене
```

## Команды бота

| Команда | Действие |
|---------|---------|
| `/start` | Приветствие, регистрация пользователя |
| `/scene <описание>` | Создать диалог-сцену по описанию |
| `/skills` | Показать текущие уровни характеристик |
| `/new` | Сбросить текущий диалог, начать заново |

## Разработка

```bash
# Установить зависимости
uv sync

# Создать .env из примера
cp .env.example .env

# Запустить локально (polling)
uv run python main.py

# Инициализировать миграции (первый раз)
uv run aerich init -t app.core.database.TORTOISE_ORM
uv run aerich init-db

# Применить миграции
uv run aerich upgrade
```

## Деплой (Railway)

1. Создай проект на Railway
2. Подключи PostgreSQL и Redis плагины
3. Задай env vars из `.env.example`
4. Деплой автоматически через Dockerfile

## Паттерны кода

- Все сервисы — async-функции, принимают `bot: Bot` или `redis: Redis` где нужно
- OpenAI вызовы используют `response_format={"type":"json_object"}` для надёжного JSON
- Тексты форматируются в HTML parse_mode (не MarkdownV2)
- Callback data всегда ≤ 64 байта — используй короткие ключи
- Tortoise модели — в `app/models/`, регистрируются в `TORTOISE_ORM` в `database.py`
