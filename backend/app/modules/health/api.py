from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorResponse

router = APIRouter(prefix="/api/v1/health", tags=["System"])


class LiveResponse(BaseModel):
    status: str
    service: str


class ReadyResponse(BaseModel):
    status: str
    postgres: bool
    redis: bool
    minio: bool
    knowledge_index: bool
    llm: bool


@router.get("/live", response_model=LiveResponse, summary="Проверка процесса")
async def live(settings: Annotated[Settings, Depends(get_settings)]) -> LiveResponse:
    return LiveResponse(status="alive", service=settings.app_name)


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={503: {"model": ErrorResponse, "description": "Зависимости ещё не готовы"}},
    summary="Проверка готовности к ответам",
)
async def ready(request: Request) -> ReadyResponse:
    infrastructure = getattr(request.app.state, "infrastructure", None)
    if infrastructure is None:
        raise AppError(503, "SERVICE_NOT_READY", "Infrastructure is not configured")
    checks: dict[str, bool] = await infrastructure.check()
    settings = get_settings()
    knowledge_index = False
    if checks["postgres"]:
        try:
            async with infrastructure.engine.connect() as connection:
                result = await connection.execute(
                    text("""SELECT EXISTS (
                          SELECT 1 FROM knowledge_chunks c
                          JOIN knowledge_document_versions v ON v.id = c.version_id
                          JOIN knowledge_documents d ON d.active_version_id = v.id
                          WHERE d.status = 'active_public' AND d.access_level = 'public'
                            AND c.embedding IS NOT NULL
                        )""")
                )
                knowledge_index = bool(result.scalar_one())
        except Exception:
            pass
    llm = False
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(settings.llm_url.rstrip("/") + "/health")
            llm = response.status_code == 200
    except httpx.HTTPError:
        pass
    status = ReadyResponse(
        status="ready" if all(checks.values()) and knowledge_index and llm else "not_ready",
        **checks,
        knowledge_index=knowledge_index,
        llm=llm,
    )
    if status.status != "ready":
        raise AppError(503, "SERVICE_NOT_READY", "Service is not ready", status.model_dump())
    return status
