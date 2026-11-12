"""Extract text from source documents for downstream processing."""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
TEXT_DIR = PROJECT_ROOT / "data" / "text"


def extract_text(source: Path) -> str:
    """Extract text from a PDF, plain-text, or HTML source."""
    suffix = source.suffix.lower()
    if suffix in {".txt", ".html", ".htm"}:
        return source.read_text(encoding="utf-8")
    if suffix == ".pdf":
        with fitz.open(source) as document:
            return "\n".join(page.get_text() for page in document)
    else:
        raise ValueError(f"Unsupported source type: {source.suffix}")


def save_processed_text(text: str, destination: Path) -> Path:
    """Save extracted text to the processed-data directory."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination


def extract_directory(source_dir: Path = RAW_DIR, destination_dir: Path = TEXT_DIR) -> list[Path]:
    """Extract every supported source below ``source_dir``."""
    created: list[Path] = []
    for source in sorted(source_dir.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in {".pdf", ".txt", ".html", ".htm"}:
            continue
        relative_destination = source.relative_to(source_dir).with_suffix(".txt")
        destination = destination_dir / relative_destination
        save_processed_text(extract_text(source), destination)
        created.append(destination)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract source documents into data/text.")
    parser.add_argument("--source", type=Path, default=RAW_DIR, help="Source directory (default: data/raw)")
    parser.add_argument(
        "--destination",
        type=Path,
        default=TEXT_DIR,
        help="Output directory (default: data/text)",
    )
    args = parser.parse_args()

    created = extract_directory(args.source, args.destination)
    for destination in created:
        print(f"Created {destination}")
    print(f"Extracted {len(created)} document(s).")


if __name__ == "__main__":
    main()

