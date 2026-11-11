from pathlib import Path

import pytest

from app.modules.knowledge.github_source import is_knowledge_path
from app.modules.knowledge.parsing import chunk_document, parse_document, validate_path


def test_only_knowledge_documents_are_selected() -> None:
    assert is_knowledge_path("23.pdf")
    assert is_knowledge_path("knowledge/admissions.md")
    assert not is_knowledge_path("README.md")
    assert not is_knowledge_path("backend/docs/architecture/architecture.md")


def test_unsafe_and_unknown_source_paths_are_rejected() -> None:
    for path in ("../secret.pdf", "/tmp/file.pdf", "knowledge/data.exe"):
        with pytest.raises(ValueError):
            validate_path(path)


def test_real_pdf_is_parsed_with_page_citations_and_deterministic_chunks() -> None:
    source = Path(__file__).resolve().parents[2] / "3.pdf"
    pages = parse_document(source.name, source.read_bytes())
    chunks = chunk_document(pages)
    assert pages and chunks
    assert all(chunk.page_number is not None for chunk in chunks)
    assert chunks == chunk_document(pages)
    assert "мониторинг" in " ".join(page_text for _, page_text in pages).lower()


def test_empty_document_and_invalid_json_fail_closed() -> None:
    with pytest.raises(ValueError):
        parse_document("knowledge/empty.txt", b"")
    with pytest.raises(ValueError):
        parse_document("knowledge/data.json", b"{")
