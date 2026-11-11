"""Embed unindexed active chunks using the configured local model."""

import asyncio

from sqlalchemy import text

from app.core.config import get_settings
from app.infrastructure.resources import Infrastructure
from app.modules.rag.embedding import LocalEmbedder


async def main() -> None:
    settings = get_settings()
    resources = Infrastructure.from_settings(settings)
    embedder = LocalEmbedder(settings.embedding_model, settings.embedding_cache_dir)
    count = 0
    try:
        async with resources.engine.connect() as conn:
            result = await conn.execute(
                text("""SELECT c.id, c.text FROM knowledge_chunks c
                     JOIN knowledge_documents d ON d.active_version_id = c.version_id
                     WHERE c.embedding IS NULL OR c.embedding_model != :model
                     ORDER BY c.id"""),
                {"model": embedder.model_name},
            )
            rows = result.fetchall()
        for offset in range(0, len(rows), 16):
            batch = rows[offset : offset + 16]
            vectors = await embedder.embed([row.text for row in batch])
            async with resources.engine.begin() as conn:
                for row, vector in zip(batch, vectors, strict=True):
                    literal = "[" + ",".join(str(value) for value in vector) + "]"
                    await conn.execute(
                        text("""UPDATE knowledge_chunks
                             SET embedding=CAST(:embedding AS vector(384)), embedding_model=:model
                             WHERE id=:id"""),
                        {"embedding": literal, "model": embedder.model_name, "id": row.id},
                    )
                    count += 1
        print({"embedded": count, "model": embedder.model_name})
    finally:
        await resources.close()


if __name__ == "__main__":
    asyncio.run(main())
