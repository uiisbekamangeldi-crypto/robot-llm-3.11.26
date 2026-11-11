# Unitree G1 EDU+ — локальный университетский AI-ассистент

Рабочий backend находится в стадии интеграции. FastAPI принимает текст и PCM WAV, PostgreSQL хранит документы и диалоги, pgvector ищет фрагменты, Redis обслуживает очередь и лимит запросов, MinIO хранит оригиналы. Локальные модели: multilingual FastEmbed, Qwen2.5 через llama.cpp, Faster Whisper и Piper. Роботный SDK пока не подключён.

## Быстрый запуск на AI Host

Требуется Python 3.12, Docker и локальные файлы моделей. Из `backend/`:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
# Замените все change-me и задайте длинный DIALOG_API_KEY.
docker compose up -d postgres redis minio
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.init_storage
.venv/bin/python -m scripts.sync_knowledge
.venv/bin/python -m scripts.embed_knowledge
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Для LLM нужен локальный `llama-server` с GGUF-файлом Qwen2.5-1.5B-Instruct Q4_K_M. В `.env` задайте `LLM_URL` и `LLM_MODEL`. Модели FastEmbed, Faster Whisper и Piper хранятся в `.models/` и не включаются в Git. Готовые Docker-сервисы `api`, `worker`, `llm` описаны в `compose.yaml`, однако полный стек в контейнерах ещё проверяется; пока надёжнее запускать Python API на AI Host, а контейнеры использовать для инфраструктуры.

Swagger: `http://127.0.0.1:8000/docs`. API: `POST /api/v1/dialog/text` с JSON `{ "question": "...", "language": "ru" }`; `POST /api/v1/dialog/audio?language=ru` с телом PCM WAV и заголовком `Content-Type: audio/wav`. Аудиоответ возвращается в JSON как `audio_wav_base64`. Если настроен `DIALOG_API_KEY`, передавайте `X-API-Key`.

Документы из GitHub загружаются со статусом `pending_review` и уровнем `internal`. Публичные ответы по ним намеренно закрыты до проверки права публикации и актуальности. Без одобренного источника API возвращает честный ответ об отсутствии подтверждения. `GET /api/v1/health/ready` будет 503, пока нет одобренных публичных фрагментов и доступной LLM.

## Проверка

```bash
.venv/bin/ruff check .
.venv/bin/mypy app
.venv/bin/pytest -q
```

Mock-агент без Unitree SDK: `python -m robot_agent.agent --host http://127.0.0.1:8000 --robot-id g1-test --input-wav question.wav --output-wav answer.wav --language ru`. Ключ передаётся через переменную окружения `ROBOT_LLM_API_KEY`.

## Состояние и ограничения

Подробный checkpoint: [docs/implementation-checkpoint.md](docs/implementation-checkpoint.md). Актуальная политика документов: [docs/architecture/source-policy.md](docs/architecture/source-policy.md). Нельзя считать качество KK/RU/EN речи подтверждённым на живом микрофоне по тестам с синтетическими WAV. Подключение Unitree SDK2/AudioHub ждёт подтверждённого интерфейса и доступа к роботу. Код и модели работают локально, облачные AI API не используются.
