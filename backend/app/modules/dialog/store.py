import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class DialogStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def find_idempotent(self, key: str) -> dict[str, Any] | None:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("""SELECT id, session_id, question, answer, language, grounded, sources
                     FROM dialog_turns WHERE idempotency_key = :key"""),
                {"key": key},
            )
            row = result.mappings().one_or_none()
            return dict(row) if row else None

    async def save(
        self,
        turn_id: UUID,
        session_id: UUID,
        request_id: UUID,
        key: str | None,
        question: str,
        answer: str,
        language: str,
        grounded: bool,
        sources: list[dict[str, Any]],
        latency_ms: int,
    ) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO dialog_sessions (id) VALUES (:id) ON CONFLICT DO NOTHING"),
                {"id": session_id},
            )
            await conn.execute(
                text("""INSERT INTO dialog_turns
                     (id, session_id, request_id, idempotency_key, question, answer,
                      language, grounded, sources, latency_ms)
                     VALUES (:id, :session_id, :request_id, :key, :question, :answer,
                             :language, :grounded, CAST(:sources AS jsonb), :latency_ms)"""),
                {
                    "id": turn_id,
                    "session_id": session_id,
                    "request_id": request_id,
                    "key": key,
                    "question": question,
                    "answer": answer,
                    "language": language,
                    "grounded": grounded,
                    "sources": json.dumps(sources),
                    "latency_ms": latency_ms,
                },
            )
