"""Queue one manual GitHub knowledge sync using Redis."""

import asyncio

from app.core.config import get_settings
from app.infrastructure.resources import Infrastructure
from app.modules.knowledge.ingestion import IngestionService


async def main() -> None:
    settings = get_settings()
    resources = Infrastructure.from_settings(settings)
    try:
        job_id = await IngestionService(settings, resources).enqueue()
        print({"job_id": str(job_id)})
    finally:
        await resources.close()


if __name__ == "__main__":
    asyncio.run(main())
