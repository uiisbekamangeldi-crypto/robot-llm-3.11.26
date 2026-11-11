import asyncio
import base64
import hashlib
import json
import secrets
import time
from typing import Literal, cast
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.errors import AppError, ErrorResponse
from app.modules.audio.stt import LocalSpeechRecognizer
from app.modules.audio.tts import LocalSpeechSynthesizer
from app.modules.dialog.language import detect_text_language
from app.modules.dialog.store import DialogStore
from app.modules.llm.grounded import grounded_answer
from app.modules.llm.local_client import LocalLLM
from app.modules.rag.embedding import LocalEmbedder
from app.modules.rag.search import KnowledgeSearch


async def require_dialog_key(request: Request) -> None:
    settings = get_settings()
    if not settings.dialog_api_key:
        if settings.app_env == "production":
            raise AppError(503, "AUTH_NOT_CONFIGURED", "Dialog authentication is not configured")
        return
    supplied = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(supplied, settings.dialog_api_key):
        raise AppError(401, "UNAUTHORIZED", "Invalid API key")
    infrastructure = getattr(request.app.state, "infrastructure", None)
    if infrastructure is None:
        raise AppError(503, "SERVICE_NOT_READY", "Rate limiter is unavailable")
    digest = hashlib.sha256(settings.dialog_api_key.encode()).hexdigest()[:16]
    bucket = f"dialog-rate:{digest}:{int(time.time() // 60)}"
    try:
        count = await infrastructure.redis.incr(bucket)
        if count == 1:
            await infrastructure.redis.expire(bucket, 120)
    except Exception as exc:
        raise AppError(503, "SERVICE_NOT_READY", "Rate limiter is unavailable") from exc
    if count > 60:
        raise AppError(429, "RATE_LIMITED", "Too many requests")


router = APIRouter(
    prefix="/api/v1/dialog", tags=["Dialog"], dependencies=[Depends(require_dialog_key)]
)


class TextQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: Literal["kk", "ru", "en"] | None = None
    session_id: UUID | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class SourceReference(BaseModel):
    document_id: UUID
    version_id: UUID
    source_path: str
    source_url: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)


class TextAnswer(BaseModel):
    turn_id: UUID
    session_id: UUID | None = None
    answer: str
    language: Literal["kk", "ru", "en"]
    grounded: bool
    sources: list[SourceReference]


class AudioAnswer(BaseModel):
    transcript: str
    answer: TextAnswer
    audio_wav_base64: str


@router.post(
    "/text",
    response_model=TextAnswer,
    responses={503: {"model": ErrorResponse, "description": "База знаний ещё не подключена"}},
    summary="Задать текстовый вопрос",
    description="Ответ только по одобренным публичным документам.",
)
async def ask_text(question: TextQuestion, request: Request) -> TextAnswer:
    infrastructure = getattr(request.app.state, "infrastructure", None)
    if infrastructure is None:
        raise AppError(503, "KNOWLEDGE_NOT_READY", "Knowledge index is not configured")
    settings = get_settings()
    language = question.language or detect_text_language(question.question)
    store = DialogStore(infrastructure.engine)
    if question.idempotency_key:
        try:
            existing = await store.find_idempotent(question.idempotency_key)
        except SQLAlchemyError as exc:
            raise AppError(503, "DATABASE_UNAVAILABLE", "Dialog store is unavailable") from exc
        if existing:
            if (
                existing["question"] != question.question
                or existing["language"] != language
                or question.session_id is not None
                and existing["session_id"] != question.session_id
            ):
                raise AppError(409, "IDEMPOTENCY_CONFLICT", "Key was used for another request")
            stored_sources = existing["sources"]
            if isinstance(stored_sources, str):
                stored_sources = json.loads(stored_sources)
            return TextAnswer(
                turn_id=existing["id"],
                session_id=existing["session_id"],
                answer=existing["answer"],
                language=language,
                grounded=existing["grounded"],
                sources=[SourceReference.model_validate(item) for item in stored_sources],
            )
    started = time.monotonic()
    try:
        embedder = cast(LocalEmbedder | None, getattr(request.app.state, "embedder", None))
        if embedder is None:
            embedder = await asyncio.to_thread(
                LocalEmbedder, settings.embedding_model, settings.embedding_cache_dir
            )
            request.app.state.embedder = embedder
        search = KnowledgeSearch(
            infrastructure.engine, embedder, settings.rag_top_k, settings.rag_max_distance
        )
        chunks = await search.search(question.question, public_only=True)
        llm = LocalLLM(settings.llm_url, settings.llm_model, settings.llm_timeout_seconds)
        result = await grounded_answer(question.question, language, chunks, llm.generate)
    except (OSError, RuntimeError, ValueError, httpx.HTTPError) as exc:
        raise AppError(503, "INFERENCE_UNAVAILABLE", "Local inference is unavailable") from exc
    answer = TextAnswer(
        turn_id=uuid4(),
        session_id=question.session_id or uuid4(),
        answer=result.text,
        language=language,
        grounded=result.grounded,
        sources=[
            SourceReference(
                document_id=source.document_id,
                version_id=source.version_id,
                source_path=source.source_path,
                source_url=(
                    f"{settings.knowledge_repository}/blob/{source.source_commit}/"
                    f"{quote(source.source_path, safe='/')}"
                ),
                page_start=source.page_number or 1,
                page_end=source.page_number or 1,
            )
            for source in result.sources
        ],
    )
    assert answer.session_id is not None
    try:
        await store.save(
            turn_id=answer.turn_id,
            session_id=answer.session_id,
            request_id=request.state.request_id,
            key=question.idempotency_key,
            question=question.question,
            answer=answer.answer,
            language=language,
            grounded=answer.grounded,
            sources=[source.model_dump(mode="json") for source in answer.sources],
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    except SQLAlchemyError as exc:
        raise AppError(503, "DATABASE_UNAVAILABLE", "Dialog store is unavailable") from exc
    return answer


@router.post("/audio", response_model=AudioAnswer, summary="Задать вопрос в формате PCM WAV")
async def ask_audio(
    request: Request,
    language: Literal["kk", "ru", "en"] | None = None,
    session_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> AudioAnswer:
    if request.headers.get("content-type", "").split(";")[0] != "audio/wav":
        raise AppError(415, "UNSUPPORTED_AUDIO", "Expected audio/wav")
    parts: list[bytes] = []
    size = 0
    async for part in request.stream():
        size += len(part)
        if size > 10_000_000:
            raise AppError(413, "AUDIO_TOO_LARGE", "Audio exceeds 10 MB")
        parts.append(part)
    data = b"".join(parts)
    settings = get_settings()
    recognizer = cast(LocalSpeechRecognizer | None, getattr(request.app.state, "recognizer", None))
    if recognizer is None:
        recognizer = LocalSpeechRecognizer(
            settings.stt_model,
            settings.embedding_cache_dir + "/whisper",
            settings.stt_timeout_seconds,
        )
        request.app.state.recognizer = recognizer
    try:
        transcript = await recognizer.transcribe(data, language)
    except ValueError as exc:
        raise AppError(422, "INVALID_AUDIO", str(exc)) from exc
    except (OSError, RuntimeError, TimeoutError) as exc:
        raise AppError(503, "STT_UNAVAILABLE", "Local speech recognition is unavailable") from exc
    if not transcript.text:
        raise AppError(422, "NO_SPEECH", "No speech detected")
    detected = transcript.language if transcript.language in {"kk", "ru", "en"} else None
    response_language = language or detected
    if response_language is None:
        raise AppError(422, "UNSUPPORTED_LANGUAGE", "Speech language is unsupported")
    answer = await ask_text(
        TextQuestion(
            question=transcript.text,
            language=response_language,
            session_id=session_id,
            idempotency_key=idempotency_key,
        ),
        request,
    )
    synthesizer = cast(
        LocalSpeechSynthesizer | None, getattr(request.app.state, "synthesizer", None)
    )
    if synthesizer is None:
        synthesizer = LocalSpeechSynthesizer(settings.tts_voice_dir, settings.tts_timeout_seconds)
        request.app.state.synthesizer = synthesizer
    try:
        wav = await synthesizer.synthesize(answer.answer, response_language)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        raise AppError(503, "TTS_UNAVAILABLE", "Local speech synthesis is unavailable") from exc
    return AudioAnswer(
        transcript=transcript.text,
        answer=answer,
        audio_wav_base64=base64.b64encode(wav).decode("ascii"),
    )
