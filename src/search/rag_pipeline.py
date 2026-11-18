"""Local retrieval and answer-generation boundary for DawaCheck."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from src.llm import ask
from src.search.bm25 import retrieve_bm25


ROOT = Path(__file__).resolve().parents[2]
MAX_CONTEXT_CHARS = 12000


@dataclass(frozen=True)
class SourceDocument:
    """A retrieved source excerpt used to ground an answer."""

    title: str
    content: str
    source: str
    official_url: str = ""


def _source_urls() -> dict[str, str]:
    provenance = ROOT / "data" / "provenance.csv"
    try:
        with provenance.open(encoding="utf-8", newline="") as handle:
            return {
                Path(row["text_path"]).name: row["url"]
                for row in csv.DictReader(handle)
                if row.get("text_path") and row.get("url")
            }
    except (OSError, UnicodeError, KeyError) as error:
        raise RuntimeError(f"Could not read source metadata {provenance}") from error


def retrieve_documents(question: str, top_k: int = 4) -> list[SourceDocument]:
    """Retrieve the most relevant local text excerpts for a question."""
    source_urls = _source_urls()
    candidates = retrieve_bm25(question, top_k=top_k * 5)
    selected: list[SourceDocument] = []
    selected_resources: set[str] = set()
    for candidate in candidates:
        source = candidate["source"]
        title = Path(source).name
        document = SourceDocument(
            title=title,
            content=candidate["text"],
            source=source,
            official_url=source_urls.get(title, ""),
        )
        resource_key = document.title
        if resource_key in selected_resources:
            continue
        selected_resources.add(resource_key)
        selected.append(document)
        if len(selected) == top_k:
            break
    return selected


def build_context(documents: list[SourceDocument]) -> str:
    """Format retrieved documents as a bounded model context."""
    context = "\n\n".join(
        f"Source: {document.title} ({document.official_url or document.source})\n"
        f"{document.content}"
        for document in documents
    )
    return context[:MAX_CONTEXT_CHARS]


def answer_question(
    question: str,
    documents: list[SourceDocument] | None = None,
    run: int = 0,
    temperature: float = 0.3,
) -> str:
    """Answer a question using retrieved local source excerpts."""
    if not question.strip():
        raise ValueError("Question must not be empty.")
    if documents is None:
        documents = retrieve_documents(question)
    if not documents:
        return "No source documents were retrieved. Please add trusted documents first."
    prompt = f"""Réponds à la question uniquement à partir des sources locales ci-dessous.
Si les sources ne contiennent pas l'information, dis-le clairement et n'invente pas.
Cite les sources utilisées entre crochets, par exemple [nom_du_fichier].

Question : {question}

Sources locales :
{build_context(documents)}
"""
    return ask(
        prompt,
        system=(
            "Tu es un assistant pharmaceutique prudent. "
            "Tu utilises exclusivement le contexte fourni et tu signales les limites."
        ),
        run=run,
        temperature=temperature,
    )

