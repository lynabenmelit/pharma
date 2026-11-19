"""P4 -- Semantic retrieval over the FAISS index built by P3.

Usage (from the repository root):

    python src\\search\\semantic.py "Quelle est la posologie du bisoprolol ?"
    python src\\search\\semantic.py "..." --top-k 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from embedder import ModelSpec, encode_queries, load_model  # noqa: E402
from vector_store import VectorStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
VECTOR_DIR = ROOT / "data" / "vector_db"
META_NAME = "chunk_metadata.json"
INFO_NAME = "index_info.json"


class SemanticRetriever:
    def __init__(self, vector_dir: Path = VECTOR_DIR, device: str | None = None) -> None:
        try:
            info = json.loads(
                (vector_dir / INFO_NAME).read_text(encoding="utf-8"))
            self.metadata: list[dict[str, Any]] = json.loads(
                (vector_dir / META_NAME).read_text(encoding="utf-8")
            )
            self.store = VectorStore.load(vector_dir)
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Could not load the vector index from {vector_dir}. "
                "Run: python src\\search\\build_faiss_index.py"
            ) from error

        if self.store.ntotal != len(self.metadata):
            raise RuntimeError(
                f"Index has {self.store.ntotal} vectors but metadata has "
                f"{len(self.metadata)} chunks: rebuild the index "
                "(python src\\search\\build_faiss_index.py)."
            )

        self.model, _ = load_model(info["model_key"], device=device)
        self.spec = ModelSpec(
            info["model"], info.get("query_prefix", ""), info.get(
                "passage_prefix", "")
        )

    def retrieve(self, question: str, top_k: int = 4) -> list[dict[str, Any]]:
        if not question.strip():
            raise ValueError("Question must not be empty.")
        if top_k <= 0:
            return []
        query = encode_queries(self.model, self.spec, [question])
        scores, ids = self.store.search(query, top_k)
        results: list[dict[str, Any]] = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0:
                continue
            chunk = self.metadata[int(idx)]
            results.append(
                {
                    "id": chunk["chunk_id"],
                    "text": chunk["text"],
                    "score": float(score),
                    "source": chunk.get("document_path") or chunk.get("source", ""),
                }
            )
        return results


_RETRIEVER: SemanticRetriever | None = None


def retrieve_semantic(question: str, top_k: int = 4) -> list[dict[str, Any]]:
    """Retrieve ``top_k`` chunks as ``id``, ``text``, ``score``, and ``source``."""
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = SemanticRetriever()
    return _RETRIEVER.retrieve(question, top_k=top_k)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()
    for rank, hit in enumerate(retrieve_semantic(args.question, args.top_k), 1):
        print(f"{rank}. [{hit['score']:.3f}] {hit['id']} | {hit['source']}")
        print(f"   {hit['text'][:160].replace(chr(10), ' ')}...")
