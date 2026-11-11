import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from docx import Document
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".json"}
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class Chunk:
    index: int
    page_number: int | None
    text: str
    checksum_sha256: str


def validate_path(path: str) -> str:
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or pure.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported or unsafe source path")
    return str(pure)


def parse_document(path: str, content: bytes) -> list[tuple[int | None, str]]:
    path = validate_path(path)
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("Document is empty or too large")
    suffix = PurePosixPath(path).suffix.lower()
    pages: list[tuple[int | None, str]]
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF signature")
        reader = PdfReader(io.BytesIO(content))
        pages = [(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
    elif suffix == ".docx":
        if not content.startswith(b"PK"):
            raise ValueError("Invalid DOCX signature")
        document = Document(io.BytesIO(content))
        pages = [(None, "\n".join(paragraph.text for paragraph in document.paragraphs))]
    else:
        decoded = content.decode("utf-8-sig")
        if suffix == ".json":
            decoded = json.dumps(json.loads(decoded), ensure_ascii=False, indent=2)
        pages = [(None, decoded)]
    normalized: list[tuple[int | None, str]] = [
        (number, re.sub(r"\s+", " ", text).strip()) for number, text in pages
    ]
    if not any(text for _, text in normalized):
        raise ValueError("Document has no extractable text")
    return normalized


def chunk_document(
    pages: list[tuple[int | None, str]], size: int = 1800, overlap: int = 250
) -> list[Chunk]:
    if size <= overlap or overlap < 0:
        raise ValueError("Invalid chunk size or overlap")
    chunks: list[Chunk] = []
    for page_number, text in pages:
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            if end < len(text):
                boundary = text.rfind(" ", start + size // 2, end)
                if boundary > start:
                    end = boundary
            part = text[start:end].strip()
            if part:
                chunks.append(
                    Chunk(len(chunks), page_number, part, hashlib.sha256(part.encode()).hexdigest())
                )
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks
