from uuid import uuid4

import pytest

from app.modules.llm.grounded import grounded_answer
from app.modules.rag.search import RetrievedChunk


def chunk() -> RetrievedChunk:
    return RetrievedChunk(uuid4(), uuid4(), uuid4(), "23.pdf", "a" * 40, 1, "Ректор — пример.", 0.2)


@pytest.mark.asyncio
async def test_no_context_never_calls_model() -> None:
    async def fail_if_called(_system: str, _user: str) -> str:
        raise AssertionError("LLM must not run without context")

    result = await grounded_answer("Кто ректор?", "ru", [], fail_if_called)
    assert not result.grounded
    assert result.sources == ()


@pytest.mark.asyncio
async def test_model_cannot_invent_source_citation() -> None:
    async def generated(_system: str, _user: str) -> str:
        return "Неподтверждённый факт. [S9]"

    result = await grounded_answer("Кто ректор?", "ru", [chunk()], generated)
    assert not result.grounded
    assert result.sources == ()


@pytest.mark.asyncio
async def test_valid_citation_resolves_to_supplied_chunk() -> None:
    source = chunk()

    async def generated(_system: str, _user: str) -> str:
        return "Ректор — пример. [S1]"

    result = await grounded_answer("Кто ректор?", "ru", [source], generated)
    assert result.grounded
    assert result.sources == (source,)


@pytest.mark.asyncio
async def test_exact_quote_without_citation_gets_verified_citation() -> None:
    source = chunk()

    async def generated(_system: str, _user: str) -> str:
        return "Ректор — пример."

    result = await grounded_answer("Кто ректор?", "ru", [source], generated)
    assert result.grounded
    assert result.text == "Ректор — пример. [S1]"


@pytest.mark.asyncio
async def test_citation_without_matching_quote_is_rejected() -> None:
    async def generated(_system: str, _user: str) -> str:
        return "Другой человек занимает должность. [S1]"

    result = await grounded_answer("Кто ректор?", "ru", [chunk()], generated)
    assert not result.grounded
