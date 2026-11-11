import asyncio
import hashlib
import io
from collections.abc import Awaitable
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import cast
from uuid import UUID, uuid4

import httpx
from sqlalchemy import text

from app.core.config import Settings
from app.infrastructure.resources import Infrastructure
from app.modules.knowledge.github_source import GitHubFile, GitHubSource
from app.modules.knowledge.parsing import chunk_document, parse_document


class IngestionService:
    def __init__(self, settings: Settings, infrastructure: Infrastructure) -> None:
        self.resources = infrastructure
        self.source = GitHubSource(
            settings.knowledge_repository, settings.knowledge_branch, settings.github_token
        )

    async def enqueue(self) -> UUID:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            commit, _ = await self.source.snapshot(client)
        source_id = await self._source_id()
        job_id = uuid4()
        async with self.resources.engine.begin() as conn:
            result = await conn.execute(
                text("""INSERT INTO ingestion_jobs (id, source_id, source_commit, status)
                     VALUES (:id, :source_id, :commit, 'queued')
                     ON CONFLICT (source_id, source_commit) DO NOTHING
                     RETURNING id"""),
                {"id": job_id, "source_id": source_id, "commit": commit},
            )
            inserted = result.scalar_one_or_none()
        if inserted is not None:
            await cast(Awaitable[int], self.resources.redis.lpush("knowledge:sync", commit))
        return job_id if inserted is not None else await self._job_id(source_id, commit)

    async def _job_id(self, source_id: UUID, commit: str) -> UUID:
        async with self.resources.engine.connect() as conn:
            result = await conn.execute(
                text("""SELECT id FROM ingestion_jobs
                     WHERE source_id=:source_id AND source_commit=:commit"""),
                {"source_id": source_id, "commit": commit},
            )
            return cast(UUID, result.scalar_one())

    async def sync(self, expected_commit: str | None = None) -> dict[str, int | str]:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            commit, files = await self.source.snapshot(client)
            if expected_commit is not None and commit != expected_commit:
                source_id = await self._source_id()
                await self._finish_job(source_id, expected_commit, "failed", "SOURCE_MOVED")
                raise ValueError("Source branch moved after job was queued")
            source_id = await self._source_id()
            job_id = uuid4()
            async with self.resources.engine.begin() as conn:
                await conn.execute(
                    text("""INSERT INTO ingestion_jobs (id, source_id, source_commit, status)
                         VALUES (:id, :source_id, :commit, 'running')
                         ON CONFLICT (source_id, source_commit) DO NOTHING"""),
                    {"id": job_id, "source_id": source_id, "commit": commit},
                )
                await conn.execute(
                    text("""UPDATE ingestion_jobs SET status='running', error_code=NULL,
                         finished_at=NULL WHERE source_id=:source_id AND source_commit=:commit"""),
                    {"source_id": source_id, "commit": commit},
                )
            processed = 0
            skipped = 0
            try:
                for file in files:
                    data = await self.source.download(client, commit, file)
                    if await self._ingest_file(source_id, commit, file, data):
                        processed += 1
                    else:
                        skipped += 1
                await self._mark_missing(source_id, {file.path for file in files})
            except Exception:
                await self._finish_job(source_id, commit, "failed", "INGESTION_FAILED")
                raise
            await self._finish_job(source_id, commit, "completed", None)
            return {"commit": commit, "processed": processed, "skipped": skipped}

    async def _source_id(self) -> UUID:
        async with self.resources.engine.begin() as conn:
            source_id = uuid4()
            result = await conn.execute(
                text("""INSERT INTO knowledge_sources (id, repository_url, branch)
                     VALUES (:id, :url, :branch)
                     ON CONFLICT (repository_url) DO UPDATE SET branch = EXCLUDED.branch
                     RETURNING id"""),
                {"id": source_id, "url": self.source.repository_url, "branch": self.source.branch},
            )
            return cast(UUID, result.scalar_one())

    async def _ingest_file(
        self, source_id: UUID, commit: str, file: GitHubFile, data: bytes
    ) -> bool:
        checksum = hashlib.sha256(data).hexdigest()
        pages = parse_document(file.path, data)
        chunks = chunk_document(pages)
        status = (
            "metadata_only"
            if PurePosixPath(file.path).name == "Каталог знаний.pdf"
            else "pending_review"
        )
        if PurePosixPath(file.path).name == "5.pdf":
            status = "superseded"
        document_id = uuid4()
        version_id = uuid4()
        storage_key = f"knowledge/{source_id}/{checksum}/{PurePosixPath(file.path).name}"
        async with self.resources.engine.begin() as conn:
            existing = await conn.execute(
                text("""SELECT v.id FROM knowledge_document_versions v
                     JOIN knowledge_documents d ON d.id = v.document_id
                     WHERE d.source_id=:source_id AND d.source_path=:path
                     AND v.checksum_sha256=:checksum"""),
                {"source_id": source_id, "path": file.path, "checksum": checksum},
            )
            if existing.scalar_one_or_none() is not None:
                return False
        await asyncio.to_thread(
            self.resources.minio.put_object,
            self.resources.bucket,
            storage_key,
            io.BytesIO(data),
            len(data),
            content_type="application/octet-stream",
        )
        async with self.resources.engine.begin() as conn:
            result = await conn.execute(
                text("""INSERT INTO knowledge_documents
                     (id, source_id, source_path, title, status, access_level)
                     VALUES (:id, :source_id, :path, :title, :status, 'internal')
                     ON CONFLICT (source_id, source_path) DO UPDATE
                     SET title=EXCLUDED.title, status=EXCLUDED.status
                     RETURNING id"""),
                {
                    "id": document_id,
                    "source_id": source_id,
                    "path": file.path,
                    "title": PurePosixPath(file.path).stem,
                    "status": status,
                },
            )
            document_id = result.scalar_one()
            await conn.execute(
                text("""INSERT INTO knowledge_document_versions
                     (id, document_id, source_commit, checksum_sha256, storage_key)
                     VALUES (:id, :document_id, :commit, :checksum, :storage_key)"""),
                {
                    "id": version_id,
                    "document_id": document_id,
                    "commit": commit,
                    "checksum": checksum,
                    "storage_key": storage_key,
                },
            )
            for chunk in chunks:
                await conn.execute(
                    text("""INSERT INTO knowledge_chunks
                         (id, version_id, chunk_index, page_number, text, checksum_sha256)
                         VALUES (:id, :version_id, :chunk_index, :page_number,
                                 :text, :checksum)"""),
                    {
                        "id": uuid4(),
                        "version_id": version_id,
                        "chunk_index": chunk.index,
                        "page_number": chunk.page_number,
                        "text": chunk.text,
                        "checksum": chunk.checksum_sha256,
                    },
                )
            await conn.execute(
                text(
                    "UPDATE knowledge_documents SET active_version_id=:version WHERE id=:document"
                ),
                {"version": version_id, "document": document_id},
            )
        return True

    async def _mark_missing(self, source_id: UUID, paths: set[str]) -> None:
        async with self.resources.engine.begin() as conn:
            result = await conn.execute(
                text("SELECT id, source_path FROM knowledge_documents WHERE source_id=:source_id"),
                {"source_id": source_id},
            )
            for document_id, path in result:
                if path not in paths:
                    await conn.execute(
                        text("UPDATE knowledge_documents SET status='missing' WHERE id=:id"),
                        {"id": document_id},
                    )

    async def _finish_job(
        self, source_id: UUID, commit: str, status: str, error: str | None
    ) -> None:
        async with self.resources.engine.begin() as conn:
            await conn.execute(
                text("""UPDATE ingestion_jobs SET status=:status, error_code=:error,
                     finished_at=:finished_at WHERE source_id=:source_id
                     AND source_commit=:commit"""),
                {
                    "status": status,
                    "error": error,
                    "finished_at": datetime.now(UTC),
                    "source_id": source_id,
                    "commit": commit,
                },
            )
