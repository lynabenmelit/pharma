import json
import tempfile
import unittest
from pathlib import Path

from src.search.bm25 import BM25Retriever, load_chunks, tokenize


class BM25Tests(unittest.TestCase):
    def test_tokenize_removes_accents(self):
        self.assertEqual(tokenize("Précautions d'emploi"), ["precautions", "d", "emploi"])

    def test_retrieves_relevant_chunks_with_required_shape(self):
        chunks = [
            {"chunk_id": "dose", "text": "La dose recommandée est de 500 mg.", "source": "notice"},
            {"chunk_id": "warning", "text": "Ne pas utiliser en cas d'allergie.", "source": "notice"},
            {"chunk_id": "other", "text": "La forme est une gélule.", "source": "notice"},
        ]
        result = BM25Retriever(chunks).retrieve("dose 500 mg", top_k=1)
        self.assertEqual(result[0]["id"], "dose")
        self.assertEqual(set(result[0]), {"id", "text", "score", "source"})
        self.assertGreater(result[0]["score"], 0)

    def test_loads_jsonl_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunks.jsonl"
            path.write_text(
                json.dumps({"chunk_id": "1", "text": "texte", "source": "test"}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(load_chunks(path)[0]["chunk_id"], "1")

    def test_metadata_improves_medical_document_ranking(self):
        chunks = [
            {
                "chunk_id": "aspirin",
                "text": "Le produit soulage la douleur légère.",
                "drug": "acide acétylsalicylique",
                "drug_norm": "acide acetylsalicylique",
                "document": "notice_aspirine.txt",
            },
            {
                "chunk_id": "diclofenac",
                "text": "Grossesse : toute prise est contre-indiquée.",
                "drug": "diclofénac",
                "drug_norm": "diclofenac",
                "document": "RCP_Biofenac.txt",
            },
        ]
        result = BM25Retriever(chunks).retrieve("diclofenac grossesse contre-indication", top_k=1)
        self.assertEqual(result[0]["id"], "diclofenac")

    def test_result_score_is_the_combined_ranking_score(self):
        chunks = [
            {
                "chunk_id": "match",
                "text": "Aspirine douleur.",
                "drug": "aspirine",
                "drug_norm": "aspirine",
                "document": "notice_aspirine.txt",
            },
            {
                "chunk_id": "bm25-only",
                "text": "Douleur aspirine notice.",
                "drug": "",
                "drug_norm": "",
                "document": "notice.txt",
            },
        ]
        retriever = BM25Retriever(chunks)
        result = retriever.retrieve("aspirine douleur", top_k=2)
        raw_scores = retriever._index.get_scores(["aspirine", "douleur"])
        combined_scores = [
            float(raw_scores[index]) + 1.5 * len(
                {"aspirine", "douleur"}.intersection(retriever._metadata_tokens[index])
            )
            for index in range(len(chunks))
        ]
        returned_by_id = {item["id"]: item["score"] for item in result}
        for index, chunk in enumerate(chunks):
            if chunk["chunk_id"] in returned_by_id:
                self.assertEqual(
                    returned_by_id[chunk["chunk_id"]],
                    combined_scores[index],
                )

    def test_no_matching_chunks_returns_empty(self):
        chunks = [
            {"chunk_id": "1", "text": "La dose est recommandée.", "source": "notice"},
            {"chunk_id": "2", "text": "Une allergie est possible.", "source": "notice"},
        ]
        result = BM25Retriever(chunks).retrieve("diclofenac périndopril", top_k=4)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
