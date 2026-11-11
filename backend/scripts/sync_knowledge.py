"""Run an explicit, one-shot GitHub knowledge sync."""

import asyncio

from app.core.config import get_settings
from app.infrastructure.resources import Infrastructure
from app.modules.knowledge.ingestion import IngestionService


async def main() -> None:
    settings = get_settings()
    resources = Infrastructure.from_settings(settings)
    try:
        result = await IngestionService(settings, resources).sync()
        print(result)
    finally:
        await resources.close()


if __name__ == "__main__":
    asyncio.run(main())
