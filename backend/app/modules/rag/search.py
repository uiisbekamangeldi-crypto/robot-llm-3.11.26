from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.rag.embedding import LocalEmbedder


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    source_path: str
    source_commit: str
    page_number: int | None
    text: str
    distance: float


class KnowledgeSearch:
    def __init__(
        self,
        engine: AsyncEngine,
        embedder: LocalEmbedder,
        top_k: int = 5,
        max_distance: float = 0.45,
    ) -> None:
        self.engine = engine
        self.embedder = embedder
        self.top_k = top_k
        self.max_distance = max_distance

    async def search(self, question: str, public_only: bool = True) -> list[RetrievedChunk]:
        if not question.strip():
            return []
        vector = (await self.embedder.embed([question]))[0]
        vector_literal = "[" + ",".join(str(value) for value in vector) + "]"
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("""SELECT c.id AS chunk_id, d.id AS document_id, v.id AS version_id,
                            d.source_path, v.source_commit, c.page_number, c.text,
                            c.embedding <=> CAST(:query AS vector(384)) AS distance
                     FROM knowledge_chunks c
                     JOIN knowledge_document_versions v ON v.id = c.version_id
                     JOIN knowledge_documents d ON d.active_version_id = v.id
                     WHERE c.embedding IS NOT NULL AND c.embedding_model = :model
                       AND d.status = :status AND d.access_level = :access
                     ORDER BY c.embedding <=> CAST(:query AS vector(384)) LIMIT :limit"""),
                {
                    "query": vector_literal,
                    "model": self.embedder.model_name,
                    "status": "active_public" if public_only else "pending_review",
                    "access": "public" if public_only else "internal",
                    "limit": self.top_k,
                },
            )
            return [
                RetrievedChunk(
                    chunk_id=row.chunk_id,
                    document_id=row.document_id,
                    version_id=row.version_id,
                    source_path=row.source_path,
                    source_commit=row.source_commit,
                    page_number=row.page_number,
                    text=row.text,
                    distance=float(row.distance),
                )
                for row in result
                if float(row.distance) <= self.max_distance
            ]
