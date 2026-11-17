"""Extract PDFs while preserving their source folders under data/text."""
import re
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW = PROJECT_ROOT / "data" / "raw"
OUT = PROJECT_ROOT / "data" / "text"


def clean(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for pdf in sorted(RAW.rglob("*.pdf")):
        with fitz.open(pdf) as doc:
            pages = [clean(page.get_text()) for page in doc]

        relative = pdf.relative_to(RAW).with_suffix(".txt")
        destination = OUT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "\n\n".join(f"[page {i+1}]\n{t}" for i, t in enumerate(pages)),
            encoding="utf-8",
        )
        n = sum(len(t) for t in pages)
        warn = "  <-- very little text, scanned PDF?" if n < 100 * len(pages) else ""
        print(f"OK: {pdf.name} -> {relative.as_posix()} ({len(pages)} pages, {n} characters){warn}")


if __name__ == "__main__":
    main()