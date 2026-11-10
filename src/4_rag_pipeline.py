"""Retrieval and answer-generation boundary for DawaCheck."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDocument:
    """A retrieved source excerpt used to ground an answer."""

    title: str
    content: str
    source: str


def build_context(documents: list[SourceDocument]) -> str:
    """Format retrieved documents as a bounded model context."""
    return "\n\n".join(
        f"Source: {document.title} ({document.source})\n{document.content}"
        for document in documents
    )


def answer_question(question: str, documents: list[SourceDocument]) -> str:
    """Return a safe placeholder until the Gemini client is configured."""
    if not question.strip():
        raise ValueError("Question must not be empty.")
    if not documents:
        return "No source documents were retrieved. Please add trusted documents first."
    return (
        "Gemini integration is not configured yet. "
        f"Retrieved context contains {len(documents)} source document(s)."
    )

