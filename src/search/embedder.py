"""Shared embedding helpers for DawaCheck semantic retrieval (P3 + P4).

The index builder (build_faiss_index.py) and the query side (P4's
retrieve_semantic) MUST use the same model and the same prefixes, otherwise
the vectors live in different spaces. Both import from this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class ModelSpec:
    hf_name: str
    query_prefix: str = ""
    passage_prefix: str = ""


# Keys are short names usable on the command line.
MODELS: dict[str, ModelSpec] = {
    # Multilingual (French / English / Arabic) -- recommended for this corpus.
    "multilingual-e5-small": ModelSpec(
        "intfloat/multilingual-e5-small", "query: ", "passage: "
    ),
    "multilingual-minilm": ModelSpec(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ),
    "bge-m3": ModelSpec("BAAI/bge-m3"),  # heavier (~2 GB), best quality
    # English-only baseline from the project plan.
    "all-minilm-l6-v2": ModelSpec("sentence-transformers/all-MiniLM-L6-v2"),
}
DEFAULT_MODEL = "multilingual-e5-small"


def load_model(model_key: str = DEFAULT_MODEL, device: str | None = None):
    """Load a SentenceTransformer by short key (or any raw HF name)."""
    from sentence_transformers import SentenceTransformer  # lazy import

    spec = MODELS.get(model_key, ModelSpec(model_key))
    model = SentenceTransformer(spec.hf_name, device=device)
    # E5 / MiniLM were trained with short inputs; 512 tokens is plenty for
    # 1,500-character chunks and keeps memory predictable.
    model.max_seq_length = min(model.max_seq_length or 512, 512)
    return model, spec


def embedding_dim(model) -> int:
    """Vector size; works with old and new sentence-transformers versions."""
    getter = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
    return int(getter())


def encode(
    model,
    texts: Sequence[str],
    prefix: str = "",
    batch_size: int = 32,
    show_progress_bar: bool = False,
) -> np.ndarray:
    """Encode texts into L2-normalised float32 vectors (cosine == inner product)."""
    if not texts:
        return np.zeros((0, embedding_dim(model)), dtype="float32")
    inputs = [prefix + t for t in texts]
    vectors = model.encode(
        inputs,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=show_progress_bar,
    )
    return np.ascontiguousarray(vectors, dtype="float32")


def encode_passages(model, spec: ModelSpec, texts: Iterable[str], **kw) -> np.ndarray:
    return encode(model, list(texts), prefix=spec.passage_prefix, **kw)


def encode_queries(model, spec: ModelSpec, texts: Iterable[str], **kw) -> np.ndarray:
    return encode(model, list(texts), prefix=spec.query_prefix, **kw)
