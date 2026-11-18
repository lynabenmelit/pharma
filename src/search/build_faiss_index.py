"""P3 -- Build a FAISS index from data/chunks.jsonl.

Usage (from the repository root):

    python src\\search\\build_faiss_index.py
    python src\\search\\build_faiss_index.py --model all-minilm-l6-v2
    python src\\search\\build_faiss_index.py --batch-size 16 --device cpu

Outputs (in data/vector_db/):
    embeddings.npy      all vectors (always written)
    faiss_index.bin     FAISS IndexFlatIP (only if FAISS can load on this machine)
    chunk_metadata.json list of chunk dicts; position i == FAISS id i
    index_info.json     model, dimension, counts, chunks-file hash

Memory: chunks are encoded in batches and written into one preallocated
float32 matrix (3,330 x 384 is about 5 MB), so RAM stays low on a 16 GB machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from embedder import DEFAULT_MODEL, MODELS, embedding_dim, encode_passages, load_model  # noqa: E402
from vector_store import INDEX_NAME, VectorStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS = ROOT / "data" / "chunks.jsonl"
DEFAULT_OUT_DIR = ROOT / "data" / "vector_db"
META_NAME = "chunk_metadata.json"
INFO_NAME = "index_info.json"


def load_chunks(path: Path) -> list[dict]:
    """Read JSONL chunks, skipping blank lines and chunks with empty text."""
    if not path.exists():
        raise FileNotFoundError(f"Chunks file not found: {path}")
    chunks: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON ({exc})") from exc
            if not str(obj.get("text", "")).strip():
                continue
            chunks.append(obj)
    if not chunks:
        raise ValueError(f"No usable chunks in {path}")
    return chunks


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build_index(
    chunks_path: Path = DEFAULT_CHUNKS,
    out_dir: Path = DEFAULT_OUT_DIR,
    model_key: str = DEFAULT_MODEL,
    batch_size: int = 32,
    device: str | None = None,
    model=None,
    spec=None,
) -> dict:
    """Encode all chunks and write the FAISS index + metadata. Returns the info dict."""
    chunks = load_chunks(chunks_path)
    if model is None:
        model, spec = load_model(model_key, device=device)
    dim = embedding_dim(model)

    n = len(chunks)
    matrix = np.empty((n, dim), dtype="float32")
    started = time.time()
    for start in range(0, n, batch_size):
        batch = chunks[start : start + batch_size]
        matrix[start : start + len(batch)] = encode_passages(
            model, spec, [c["text"] for c in batch], batch_size=batch_size
        )
        done = start + len(batch)
        if (done // batch_size) % 10 == 0 or done == n:
            print(f"  encoded {done}/{n} chunks ({time.time() - started:.0f}s)")

    # Vectors are L2-normalised, so inner product == cosine similarity.
    # Exact search is ideal at this scale. Uses FAISS if it loads, NumPy otherwise.
    store = VectorStore.from_matrix(matrix)
    assert store.ntotal == n
    written = store.save(out_dir)
    print(f"  backend: {store.backend}; wrote {', '.join(written)}")

    metadata = [{"faiss_id": i, **c} for i, c in enumerate(chunks)]
    with (out_dir / META_NAME).open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False)

    info = {
        "model_key": model_key,
        "model": spec.hf_name,
        "query_prefix": spec.query_prefix,
        "passage_prefix": spec.passage_prefix,
        "dimension": dim,
        "n_chunks": n,
        "metric": "inner_product_on_normalized_vectors",
        "index_type": "IndexFlatIP" if store.backend == "faiss" else "numpy_exact",
        "backend": store.backend,
        "chunks_file": str(chunks_path),
        "chunks_sha256": sha256_file(chunks_path),
        "build_seconds": round(time.time() - started, 1),
    }
    with (out_dir / INFO_NAME).open("w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=2)
    return info


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"one of {', '.join(MODELS)} or any HF model name")
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--device", default=None, help="cpu, cuda... (default: auto)")
    args = p.parse_args()

    print(f"Building index with {args.model} from {args.chunks}")
    info = build_index(args.chunks, args.out_dir, args.model, args.batch_size, args.device)
    print(f"Done: {info['n_chunks']} chunks, dim {info['dimension']}, "
          f"{info['build_seconds']}s -> {args.out_dir}")


if __name__ == "__main__":
    main()
