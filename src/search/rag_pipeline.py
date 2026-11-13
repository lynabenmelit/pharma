"""Local retrieval and answer-generation boundary for DawaCheck."""

from __future__ import annotations

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
    "quelle", "quelles", "quel", "quels", "un", "une",
}


@dataclass(frozen=True)
class SourceDocument:
    """A retrieved source excerpt used to ground an answer."""

    title: str
    content: str
    source: str


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return set(re.findall(r"[a-z0-9]+", normalized.lower()))


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
    candidates: list[tuple[int, SourceDocument]] = []
    for text_dir in TEXT_DIRS:
        if not text_dir.exists():
            continue
        for path in text_dir.rglob("*.txt"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise RuntimeError(f"Could not read source document {path}") from error
            for chunk in _chunks(text):
                chunk_tokens = _tokens(chunk)
                score = len(query_tokens.intersection(chunk_tokens))
                filename_tokens = _tokens(path.name)
                score += 5 * len(query_tokens.intersection(filename_tokens))
                if score:
                    candidates.append(
                        (
                            score,
                            SourceDocument(
                                title=path.name,
                                content=chunk,
                                source=str(path.relative_to(ROOT)),
                            ),
                        )
                    )
        if candidates:
            break

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [document for _, document in candidates[:top_k]]


def build_context(documents: list[SourceDocument]) -> str:
    """Format retrieved documents as a bounded model context."""
    context = "\n\n".join(
        f"Source: {document.title} ({document.source})\n{document.content}"
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

