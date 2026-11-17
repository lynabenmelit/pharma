"""Split cleaned pharmaceutical documents into small passages with metadata."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
TEXT_CLEAN_DIR = ROOT / "data" / "text_clean"
CHUNKS_FILE = ROOT / "data" / "chunks.jsonl"
REPORT_FILE = ROOT / "data" / "chunks_report.json"
CLEAN_DOCS_FILE = ROOT / "data" / "clean_docs.csv"

MAX_CHUNK_CHARS = 1500
OVERLAP_CHARS = 200


def _clean_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _word_overlap(text: str, size: int) -> str:
    """Return the end of a chunk, trimmed so it starts at a word boundary."""
    if len(text) <= size:
        return text
    overlap = text[-size:]
    first_space = overlap.find(" ")
    if first_space >= 0:
        overlap = overlap[first_space + 1 :]
    return overlap.strip()


def split_long_block(block: str, max_chars: int) -> list[str]:
    """Split a paragraph that is too large without cutting a word."""
    words = block.split()
    pieces: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_text(
    text: str,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[str]:
    """Split text by paragraphs and add limited overlap between chunks."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive.")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars.")

    text = _clean_whitespace(text)
    if not text:
        return []

    chunks: list[str] = []
    current = ""

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    for paragraph in paragraphs:
        parts = [paragraph] if len(paragraph) <= max_chars else split_long_block(paragraph, max_chars)

        for part in parts:
            candidate = f"{current}\n\n{part}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                overlap = _word_overlap(current, overlap_chars)
                candidate = f"{overlap}\n\n{part}".strip()
                if len(candidate) > max_chars:
                    candidate = part
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def load_document_metadata(path: Path) -> dict[str, str]:
    """Load metadata for a cleaned document from clean_docs.csv."""
    if not CLEAN_DOCS_FILE.exists():
        return {}

    with CLEAN_DOCS_FILE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            file_name = Path(row.get("file", "").replace("\\", "/")).name
            if file_name == path.name:
                return row
    return {}


def iter_chunks(
    text_dir: Path = TEXT_CLEAN_DIR,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> Iterable[dict]:
    """Yield chunks with their document metadata."""
    for path in sorted(text_dir.rglob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        metadata = load_document_metadata(path)
        chunks = chunk_text(text, max_chars=max_chars, overlap_chars=overlap_chars)

        for index, content in enumerate(chunks):
            chunk_id = hashlib.sha256(
                f"{path.as_posix()}::{index}".encode("utf-8")
            ).hexdigest()[:16]
            yield {
                "chunk_id": chunk_id,
                "document": path.name,
                "document_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "source": metadata.get("source", path.parent.name),
                "drug": metadata.get("drug", ""),
                "drug_norm": metadata.get("drug_norm", ""),
                "url": metadata.get("url", ""),
                "language": metadata.get("language", ""),
                "authority": metadata.get("authority", ""),
                "chunk_index": index,
                "n_chunks": len(chunks),
                "n_chars": len(content),
                "text": content,
            }


def run(
    text_dir: Path = TEXT_CLEAN_DIR,
    chunks_file: Path = CHUNKS_FILE,
    report_file: Path = REPORT_FILE,
) -> dict:
    chunks_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.parent.mkdir(parents=True, exist_ok=True)

    rows = list(iter_chunks(text_dir))
    with chunks_file.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    documents = {row["document"] for row in rows}
    report = {
        "input_documents": len(documents),
        "chunk_count": len(rows),
        "max_chunk_chars": MAX_CHUNK_CHARS,
        "overlap_chars": OVERLAP_CHARS,
        "average_chunk_chars": round(
            sum(row["n_chars"] for row in rows) / len(rows), 1
        ) if rows else 0,
        "largest_chunk_chars": max((row["n_chars"] for row in rows), default=0),
        "chunks_file": str(chunks_file.relative_to(ROOT)).replace("\\", "/"),
    }
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
