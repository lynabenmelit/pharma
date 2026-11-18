"""Vector search backend: FAISS when it can be loaded, NumPy otherwise.

Some Windows machines block faiss's compiled DLL (Application Control policy).
With only a few thousand vectors, exact NumPy search is just as fast, so both
backends expose the same tiny interface used by the builder and by P4:

    store = VectorStore.from_matrix(matrix)      # build
    store.save(out_dir)                          # writes embeddings.npy (+ faiss_index.bin if possible)
    store = VectorStore.load(out_dir)            # load
    scores, ids = store.search(query_matrix, k)  # both shaped (n_queries, k)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

INDEX_NAME = "faiss_index.bin"
EMBEDDINGS_NAME = "embeddings.npy"


def try_import_faiss():
    """Return the faiss module, or None if missing or blocked by the OS."""
    try:
        import faiss  # noqa: WPS433

        return faiss
    except ImportError as exc:  # includes "DLL load failed ... Application Control"
        print(f"[vector_store] FAISS unavailable ({str(exc)[:90]}...) -> using NumPy search")
        return None


class VectorStore:
    def __init__(self, matrix: np.ndarray, faiss_index=None) -> None:
        self.matrix = np.ascontiguousarray(matrix, dtype="float32")
        self.faiss_index = faiss_index

    @property
    def backend(self) -> str:
        return "faiss" if self.faiss_index is not None else "numpy"

    @property
    def ntotal(self) -> int:
        return len(self.matrix)

    @classmethod
    def from_matrix(cls, matrix: np.ndarray) -> "VectorStore":
        faiss = try_import_faiss()
        index = None
        if faiss is not None:
            index = faiss.IndexFlatIP(matrix.shape[1])  # exact inner product
            index.add(np.ascontiguousarray(matrix, dtype="float32"))
        return cls(matrix, index)

    def save(self, out_dir: Path) -> list[str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        np.save(out_dir / EMBEDDINGS_NAME, self.matrix)
        written = [EMBEDDINGS_NAME]
        if self.faiss_index is not None:
            import faiss

            faiss.write_index(self.faiss_index, str(out_dir / INDEX_NAME))
            written.append(INDEX_NAME)
        return written

    @classmethod
    def load(cls, out_dir: Path) -> "VectorStore":
        matrix = np.load(out_dir / EMBEDDINGS_NAME)
        faiss = try_import_faiss()
        index = None
        if faiss is not None and (out_dir / INDEX_NAME).exists():
            index = faiss.read_index(str(out_dir / INDEX_NAME))
        return cls(matrix, index)

    def search(self, queries: np.ndarray, k: int = 10) -> tuple[np.ndarray, np.ndarray]:
        queries = np.ascontiguousarray(queries, dtype="float32")
        k = min(k, self.ntotal)
        if self.faiss_index is not None:
            return self.faiss_index.search(queries, k)
        sims = queries @ self.matrix.T  # cosine, vectors are normalised
        ids = np.argsort(-sims, axis=1)[:, :k]
        return np.take_along_axis(sims, ids, axis=1), ids
