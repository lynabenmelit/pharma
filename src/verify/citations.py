"""Verify that answer citations refer to actually retrieved passages."""

from __future__ import annotations

import re
from collections.abc import Iterable


CITATION_PATTERN = re.compile(r"\[([^\[\]]+)\]|【([^【】]+)】")


def verify_citations(answer: str, documents: Iterable[object]) -> dict[str, list[str]]:
    retrieved_titles = {
        str(getattr(document, "title", ""))
        for document in documents
    }
    cited = [
        (square_bracket or full_width_bracket).strip()
        for square_bracket, full_width_bracket in CITATION_PATTERN.findall(answer)
        if (square_bracket or full_width_bracket).strip()
    ]
    verified = [name for name in cited if name in retrieved_titles]
    unsupported = [name for name in cited if name not in retrieved_titles]
    return {
        "cited": cited,
        "verified": verified,
        "unsupported": unsupported,
    }
