"""BM25 keyword retrieval over prepared document chunks."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi


ROOT = Path(__file__).resolve().parents[2]
CHUNKS_FILE = ROOT / "data" / "chunks.jsonl"


def tokenize(value: str) -> list[str]:
    """Normalize accents and return searchable word tokens."""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.findall(r"[a-z0-9]+", normalized.lower())


def load_chunks(chunks_file: Path = CHUNKS_FILE) -> list[dict[str, Any]]:
    """Load prepared chunks from JSONL and validate the fields used by retrieval."""
    try:
        with chunks_file.open(encoding="utf-8-sig") as handle:
            chunks = [json.loads(line) for line in handle if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not load chunks from {chunks_file}") from error

    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict) or not chunk.get("text") or not chunk.get("chunk_id"):
            raise ValueError(f"Invalid chunk at line {index + 1} in {chunks_file}.")
    return chunks


class BM25Retriever:
    """In-memory BM25 index for the prepared chunk corpus."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = chunks
        metadata_fields = ("drug", "drug_norm", "document")
        tokenized_chunks = [
            tokenize(
                " ".join(
                    str(chunk.get(field, ""))
                    for field in ("text", "drug", "drug_norm", "document")
                )
            )
            for chunk in chunks
        ]
        self._metadata_tokens = [
            set(
                tokenize(
                    " ".join(
                        str(chunk.get(field, ""))
                        for field in metadata_fields
                    )
                )
            )
            for chunk in chunks
        ]
        self._index = BM25Okapi(tokenized_chunks) if tokenized_chunks else None

    def retrieve(self, question: str, top_k: int = 4) -> list[dict[str, Any]]:
        """Return matching chunks ordered by descending combined score."""
        if not question.strip():
            raise ValueError("Question must not be empty.")
        if top_k <= 0 or not self.chunks:
            return []

        query_tokens = tokenize(question)
        if not query_tokens:
            return []
        if self._index is None:
            return []
        scores = self._index.get_scores(query_tokens)
        query_token_set = set(query_tokens)
        combined_scores = [
            float(scores[index])
            + 1.5 * len(query_token_set.intersection(self._metadata_tokens[index]))
            for index in range(len(self.chunks))
        ]
        ranked_indexes = sorted(
            range(len(self.chunks)),
            key=lambda index: combined_scores[index],
            reverse=True,
        )
        results: list[dict[str, Any]] = []
        for index in ranked_indexes:
            score = combined_scores[index]
            if score <= 0:
                break
            chunk = self.chunks[index]
            results.append(
                {
                    "id": chunk["chunk_id"],
                    "text": chunk["text"],
                    "score": score,
                    "source": chunk.get("document_path") or chunk.get("source", ""),
                }
            )
            if len(results) == top_k:
                break
        return results


_RETRIEVER: BM25Retriever | None = None
_RETRIEVER_CHUNKS_FILE: Path | None = None


def retrieve_bm25(
    question: str,
    top_k: int = 4,
    chunks_file: Path = CHUNKS_FILE,
) -> list[dict[str, Any]]:
    """Retrieve ``top_k`` chunks as ``id``, ``text``, ``score``, and ``source``."""
    global _RETRIEVER, _RETRIEVER_CHUNKS_FILE
    if _RETRIEVER is None or chunks_file != _RETRIEVER_CHUNKS_FILE:
        _RETRIEVER = BM25Retriever(load_chunks(chunks_file))
        _RETRIEVER_CHUNKS_FILE = chunks_file
    return _RETRIEVER.retrieve(question, top_k=top_k)
