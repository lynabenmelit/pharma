import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "search"))

import build_faiss_index as b  # noqa: E402
from embedder import ModelSpec  # noqa: E402
from vector_store import VectorStore  # noqa: E402


class FakeModel:
    """Deterministic hashing-based encoder with the SentenceTransformer API."""

    def get_sentence_embedding_dimension(self):
        return 8

    def encode(self, texts, batch_size=32, normalize_embeddings=True, **_):
        out = np.zeros((len(texts), 8), "float32")
        for i, t in enumerate(texts):
            for w in t.lower().split():
                out[i, hash(w) % 8] += 1
        out /= np.linalg.norm(out, axis=1, keepdims=True) + 1e-9
        return out


class BuildIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.chunks = self.tmp / "chunks.jsonl"
        rows = [{"chunk_id": f"c{i}", "text": f"doliprane dose {i} mg", "source": "anpp"}
                for i in range(70)]
        rows.insert(3, {"chunk_id": "empty", "text": "   "})
        self.chunks.write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n\n", encoding="utf-8")

    def test_load_skips_empty(self):
        self.assertEqual(len(b.load_chunks(self.chunks)), 70)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            b.load_chunks(self.tmp / "nope.jsonl")

    def test_build_writes_aligned_outputs(self):
        out = self.tmp / "vdb"
        info = b.build_index(self.chunks, out, "fake", batch_size=16,
                             model=FakeModel(), spec=ModelSpec("fake", "q: ", "p: "))
        self.assertEqual(info["n_chunks"], 70)
        self.assertTrue((out / "embeddings.npy").exists())
        meta = json.loads((out / b.META_NAME).read_text(encoding="utf-8"))
        self.assertEqual(len(meta), 70)
        self.assertEqual([m["faiss_id"] for m in meta], list(range(70)))
        self.assertEqual(meta[0]["chunk_id"], "c0")  # order preserved

    def test_search_finds_itself(self):
        out = self.tmp / "vdb2"
        b.build_index(self.chunks, out, "fake", batch_size=16,
                      model=FakeModel(), spec=ModelSpec("fake"))
        store = VectorStore.load(out)
        scores, ids = store.search(store.matrix[[5, 40]], k=3)
        self.assertEqual(ids.shape, (2, 3))
        # the fake encoder can give identical vectors to different chunks (ties)
        for row, q in enumerate((5, 40)):
            np.testing.assert_allclose(store.matrix[ids[row, 0]], store.matrix[q])
        self.assertAlmostEqual(float(scores[0, 0]), 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
