"""One Redis-backed worker for manually queued knowledge syncs."""

import asyncio
import logging
from collections.abc import Awaitable
from typing import cast

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
            interrupted = await conn.execute(
                text("SELECT source_commit FROM ingestion_jobs WHERE status='running'")
            )
            interrupted_commits = [row.source_commit for row in interrupted]
            await conn.execute(
                text("UPDATE ingestion_jobs SET status='queued' WHERE status='running'")
            )
        for commit in interrupted_commits:
            await cast(Awaitable[int], resources.redis.lpush("knowledge:sync", commit))
        if await cast(Awaitable[int], resources.redis.llen("knowledge:sync")) == 0:
            async with resources.engine.connect() as conn:
                rows = await conn.execute(
                    text("SELECT source_commit FROM ingestion_jobs WHERE status='queued'")
                )
                for row in rows:
                    await cast(
                        Awaitable[int], resources.redis.lpush("knowledge:sync", row.source_commit)
                    )
        while True:
            item = await cast(
                Awaitable[tuple[bytes, bytes] | None],
                resources.redis.brpop(["knowledge:sync"], timeout=5),
            )
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
