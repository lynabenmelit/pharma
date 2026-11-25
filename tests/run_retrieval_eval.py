"""Evaluate source hits for every test question without calling an LLM."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.normalizer import normalize_text  # noqa: E402
from src.search.build_faiss_index import load_chunks  # noqa: E402
from src.search.rag_pipeline import retrieve_documents  # noqa: E402

VECTOR_DIR = BASE / "data" / "vector_db"
CHUNKS_FILE = BASE / "data" / "chunks.jsonl"
MODES = ("bm25", "semantic", "hybrid")
OUTPUT = BASE / "reports" / "retrieval_only_30.csv"


def _validate_index() -> int:
    info = json.loads((VECTOR_DIR / "index_info.json").read_text(encoding="utf-8"))
    metadata = json.loads(
        (VECTOR_DIR / "chunk_metadata.json").read_text(encoding="utf-8")
    )
    chunks = load_chunks(CHUNKS_FILE)
    embeddings = np.load(VECTOR_DIR / "embeddings.npy", mmap_mode="r")
    chunks_hash = hashlib.sha256(CHUNKS_FILE.read_bytes()).hexdigest()

    if info.get("chunks_sha256") != chunks_hash:
        raise RuntimeError("The vector index was built from a different chunks.jsonl.")
    if info.get("n_chunks") != len(chunks):
        raise RuntimeError(
            f"Index metadata has {info.get('n_chunks')} vectors, "
            f"but chunks.jsonl has {len(chunks)} usable chunks."
        )
    if len(metadata) != len(chunks) or embeddings.shape[0] != len(chunks):
        raise RuntimeError(
            "Chunk, embedding, and metadata counts differ; rebuild the vector index."
        )
    if embeddings.shape[1] != info.get("dimension"):
        raise RuntimeError("Embedding dimension does not match index_info.json.")
    if any(
        row.get("faiss_id") != index
        or row.get("chunk_id") != chunks[index].get("chunk_id")
        for index, row in enumerate(metadata)
    ):
        raise RuntimeError("Vector IDs are not aligned with chunks.jsonl order.")
    if info.get("backend") == "faiss":
        try:
            import faiss
        except ImportError as error:
            raise RuntimeError("FAISS index is recorded but FAISS cannot be loaded.") from error
        index = faiss.read_index(str(VECTOR_DIR / "faiss_index.bin"))
        if index.ntotal != len(chunks):
            raise RuntimeError(
                f"FAISS has {index.ntotal} vectors; expected {len(chunks)}."
            )
        if index.d != embeddings.shape[1]:
            raise RuntimeError("FAISS and embedding dimensions do not match.")
    return len(chunks)


def run() -> list[dict[str, object]]:
    chunk_count = _validate_index()
    questions = json.loads(
        (BASE / "tests" / "test_questions.json").read_text(encoding="utf-8")
    )["questions"]
    missing = [question["id"] for question in questions if "expected_sources" not in question]
    if missing:
        raise ValueError(
            "Add expected_sources to every question before retrieval evaluation: "
            + ", ".join(missing)
        )

    rows: list[dict[str, object]] = []
    for question in questions:
        expected_sources = question["expected_sources"]
        for mode in MODES:
            documents = retrieve_documents(question["question"], mode=mode)
            matched = [
                source
                for source in expected_sources
                if any(
                    normalize_text(source) in normalize_text(document.title)
                    for document in documents
                )
            ]
            missing_sources = [
                source for source in expected_sources if source not in matched
            ]
            rows.append({
                "question_id": question["id"],
                "category": question.get("category", ""),
                "retrieval_mode": mode,
                "expected_sources": ", ".join(expected_sources),
                "retrieved_sources": ", ".join(document.title for document in documents),
                "matched_sources": ", ".join(matched),
                "missing_sources": ", ".join(missing_sources),
                "matched_source_count": len(matched),
                "expected_source_count": len(expected_sources),
                "source_hit_rate_percent": (
                    round(len(matched) / len(expected_sources) * 100, 1)
                    if expected_sources else ""
                ),
            })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        mode = str(row["retrieval_mode"])
        totals[mode][0] += int(row["matched_source_count"])
        totals[mode][1] += int(row["expected_source_count"])

    print(f"Index integrity: {chunk_count} chunks, vectors, and metadata entries aligned.")
    print(f"Retrieval rows: {len(rows)} (30 questions x 3 modes); no LLM calls.")
    for mode in MODES:
        matched, expected = totals[mode]
        rate = round(matched / expected * 100, 1) if expected else None
        print(f"{mode}: {matched}/{expected} expected source hits ({rate}%).")
    print(f"Saved: {OUTPUT}")
    return rows


if __name__ == "__main__":
    run()
