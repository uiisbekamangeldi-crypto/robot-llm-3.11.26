import asyncio
from dataclasses import dataclass

from minio import Minio
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings


@dataclass
class Infrastructure:
    engine: AsyncEngine
    redis: Redis
    minio: Minio
    bucket: str

    @classmethod
    def from_settings(cls, settings: Settings) -> "Infrastructure":
        if not settings.infrastructure_configured:
            raise ValueError("Database, Redis, and MinIO must all be configured")
        assert settings.database_url is not None
        assert settings.redis_url is not None
        assert settings.minio_endpoint is not None
        assert settings.minio_access_key is not None
        assert settings.minio_secret_key is not None
        if not settings.database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the asyncpg PostgreSQL driver")
        return cls(
            engine=create_async_engine(settings.database_url, pool_pre_ping=True),
            redis=Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2),
            minio=Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            ),
            bucket=settings.minio_bucket,
        )

    async def check(self) -> dict[str, bool]:
        async def check_postgres() -> bool:
            try:
                async with self.engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                    result = await connection.execute(
                        text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                    )
                    return result.scalar_one_or_none() == 1
            except Exception:
                return False

        async def check_redis() -> bool:
            try:
                return bool(await self.redis.ping())
            except Exception:
                return False

        async def check_minio() -> bool:
            try:
                return bool(await asyncio.to_thread(self.minio.bucket_exists, self.bucket))
            except Exception:
                return False

        postgres, redis, minio = await asyncio.gather(
            check_postgres(), check_redis(), check_minio()
        )
        return {"postgres": postgres, "redis": redis, "minio": minio}

    async def close(self) -> None:
        await self.engine.dispose()
        await self.redis.aclose()
