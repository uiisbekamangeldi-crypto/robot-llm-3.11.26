"""One Redis-backed worker for manually queued knowledge syncs."""

import asyncio
import logging

from sqlalchemy import text

from app.core.config import get_settings
from app.infrastructure.resources import Infrastructure
from app.modules.knowledge.ingestion import IngestionService

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    resources = Infrastructure.from_settings(settings)
    service = IngestionService(settings, resources)
    try:
        # Only one worker is configured. Recover a job interrupted by process death.
        async with resources.engine.begin() as conn:
            await conn.execute(
                text("UPDATE ingestion_jobs SET status='queued' WHERE status='running'")
            )
        if await resources.redis.llen("knowledge:sync") == 0:
            async with resources.engine.connect() as conn:
                rows = await conn.execute(
                    text("SELECT source_commit FROM ingestion_jobs WHERE status='queued'")
                )
                for row in rows:
                    await resources.redis.lpush("knowledge:sync", row.source_commit)
        while True:
            item = await resources.redis.brpop("knowledge:sync", timeout=5)
            if item is None:
                continue
            commit = item[1].decode()
            try:
                await service.sync(expected_commit=commit)
            except Exception:
                logger.exception("knowledge_sync_failed")
    finally:
        await resources.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
