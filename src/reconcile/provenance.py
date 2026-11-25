"""Reconcile provenance, accepted documents, and cleaned text files."""

from __future__ import annotations

import csv
import json
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = ROOT / "data" / "provenance.csv"
CLEAN_DOCS = ROOT / "data" / "clean_docs.csv"
REJECTED = ROOT / "data" / "rejected.csv"
TEXT_CLEAN = ROOT / "data" / "text_clean"
REPORT = ROOT / "reports" / "provenance_reconciliation.json"


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _document_key(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value.replace("\\", "/")).strip("/")
    return PurePosixPath(normalized).name.casefold()


def _path_key(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value.replace("\\", "/")).strip("/")
    return PurePosixPath(normalized).as_posix().casefold()


def reconcile(
    provenance: Path = PROVENANCE,
    clean_docs: Path = CLEAN_DOCS,
    text_clean: Path = TEXT_CLEAN,
    rejected: Path = REJECTED,
) -> dict:
    provenance_rows = _read_rows(provenance)
    clean_rows = _read_rows(clean_docs)
    rejected_rows = _read_rows(rejected)

    provenance_keys = [
        _document_key(row["text_path"])
        for row in provenance_rows
        if row.get("text_path")
    ]
    provenance_paths = [
        _path_key(row["text_path"])
        for row in provenance_rows
        if row.get("text_path")
    ]
    clean_keys = [
        _document_key(row["file"])
        for row in clean_rows
        if row.get("file")
    ]
    text_keys = [
        _document_key(path.name)
        for path in text_clean.rglob("*.txt")
    ]

    provenance_set = set(provenance_keys)
    clean_set = set(clean_keys)
    text_set = set(text_keys)
    duplicate_paths = {
        key: count
        for key, count in sorted(Counter(provenance_paths).items())
        if count > 1
    }

    return {
        "row_counts": {
            "provenance_collected": len(provenance_rows),
            "accepted_clean_docs": len(clean_rows),
            "rejected": len(rejected_rows),
        },
        "unique_document_names": {
            "provenance": len(provenance_set),
            "accepted_clean_docs": len(clean_set),
            "clean_text_files": len(text_set),
        },
        "source_counts": {
            "provenance": dict(sorted(Counter(
                row.get("source", "") for row in provenance_rows
            ).items())),
            "accepted_clean_docs": dict(sorted(Counter(
                row.get("source", "") for row in clean_rows
            ).items())),
        },
        "accepted_without_provenance": sorted(clean_set - provenance_set),
        "provenance_without_accepted_document": sorted(provenance_set - clean_set),
        "accepted_without_clean_text": sorted(clean_set - text_set),
        "clean_text_without_accepted_row": sorted(text_set - clean_set),
        "duplicate_provenance_paths": duplicate_paths,
        "provenance_rows_without_text_path": [
            row.get("doc_id", "") for row in provenance_rows if not row.get("text_path")
        ],
    }


def main() -> None:
    result = reconcile()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nSaved: {REPORT}")


if __name__ == "__main__":
    main()
