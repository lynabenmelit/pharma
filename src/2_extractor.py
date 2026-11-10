"""Extract text from source documents for downstream processing."""

from __future__ import annotations

from pathlib import Path


def extract_text(source: Path) -> str:
    """Read a plain-text or HTML source.

    PDF extraction should be added with the parser selected for this project.
    """
    if source.suffix.lower() not in {".txt", ".html", ".htm"}:
        raise ValueError(f"Unsupported source type: {source.suffix}")
    return source.read_text(encoding="utf-8")


def save_processed_text(text: str, destination: Path) -> Path:
    """Save extracted text to the processed-data directory."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination

