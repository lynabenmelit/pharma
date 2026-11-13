"""Local retrieval and answer-generation boundary for DawaCheck."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import re
import unicodedata
from pathlib import Path

from src.llm import ask


ROOT = Path(__file__).resolve().parents[2]
TEXT_DIRS = (ROOT / "data" / "text_clean", ROOT / "data" / "text")
MAX_CHUNK_CHARS = 3500
MAX_CONTEXT_CHARS = 12000
STOPWORDS = {
    "a", "au", "aux", "avec", "ce", "cette", "dans", "de", "des", "du",
    "elle", "en", "et", "est", "la", "le", "les", "ou", "pour", "que",
    "quelle", "quelles", "quel", "quels", "un", "une", "patient", "patients",
    "sous", "precaution", "precautions", "précaution", "précautions",
}


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


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized.lower())
        if len(token) > 2
    }


def _chunks(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > MAX_CHUNK_CHARS:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks


def retrieve_documents(question: str, top_k: int = 4) -> list[SourceDocument]:
    """Retrieve the most relevant local text excerpts for a question."""
    if not question.strip():
        raise ValueError("Question must not be empty.")

    query_tokens = _tokens(question) - STOPWORDS
    source_urls = _source_urls()
    candidates: list[tuple[int, SourceDocument]] = []
    seen_documents: set[str] = set()
    seen_titles: set[str] = set()
    for text_dir in TEXT_DIRS:
        if not text_dir.exists():
            continue
        for path in text_dir.rglob("*.txt"):
            if path.name in seen_titles:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise RuntimeError(f"Could not read source document {path}") from error
            document_key = str(hash(text))
            if document_key in seen_documents:
                continue
            seen_documents.add(document_key)
            seen_titles.add(path.name)
            file_tokens = _tokens(text)
            filename_tokens = _tokens(path.name)
            best_candidate: tuple[int, SourceDocument] | None = None
            for chunk in _chunks(text):
                chunk_tokens = _tokens(chunk)
                score = len(query_tokens.intersection(chunk_tokens))
                if score:
                    score += 3 * len(query_tokens.intersection(file_tokens))
                    score += 2 * len(query_tokens.intersection(filename_tokens))
                if score and (
                    best_candidate is None or score > best_candidate[0]
                ):
                    best_candidate = (
                        score,
                        SourceDocument(
                            title=path.name,
                            content=chunk,
                            source=str(path.relative_to(ROOT)),
                            official_url=source_urls.get(path.name, ""),
                        )
                    )
            if best_candidate is not None:
                candidates.append(best_candidate)

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected: list[SourceDocument] = []
    selected_resources: set[str] = set()
    for _, document in candidates:
        resource_key = document.official_url or document.source
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

