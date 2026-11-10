"""Normalize medicine names and identifiers."""

from __future__ import annotations

import re


def normalize_name(name: str) -> str:
    """Return a stable comparison form for a medicine name."""
    normalized = re.sub(r"\s+", " ", name).strip().casefold()
    return normalized


def normalize_record(record: dict[str, str]) -> dict[str, str]:
    """Normalize the medicine name in a structured record."""
    normalized = dict(record)
    if "name" in normalized:
        normalized["name"] = normalize_name(normalized["name"])
    return normalized

