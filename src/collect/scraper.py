"""Download source documents into data/raw.

This module intentionally has no network side effects on import.
"""

from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def download_document(url: str, destination: Path) -> Path:
    """Download a document from ``url`` to ``destination``."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "DawaCheck/0.1"})
    with urlopen(request, timeout=30) as response:
        destination.write_bytes(response.read())
    return destination


if __name__ == "__main__":
    print(f"Place source URLs in a script or call download_document(..., RAW_DIR / 'file').")

