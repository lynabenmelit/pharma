import unittest
from unittest.mock import patch

from src.search import rag_pipeline


class RAGPipelineTests(unittest.TestCase):
    def test_retrieve_documents_rejects_unknown_mode(self):
        with self.assertRaisesRegex(ValueError, "mode must be"):
            rag_pipeline.retrieve_documents("question", mode="unknown")

    def test_hybrid_rejects_invalid_bm25_weight(self):
        with self.assertRaisesRegex(ValueError, "bm25_weight"):
            rag_pipeline.retrieve_documents("question", mode="hybrid", bm25_weight=1.5)

    @patch("src.search.rag_pipeline.retrieve_semantic")
    @patch("src.search.rag_pipeline.retrieve_bm25")
    def test_hybrid_fuses_normalized_bm25_and_cosine_scores(self, bm25, semantic):
        bm25.return_value = [
            {"id": "a", "text": "A", "score": 1.0, "source": "a.txt"},
            {"id": "b", "text": "B", "score": 0.5, "source": "b.txt"},
        ]
        semantic.return_value = [
            {"id": "b", "text": "B", "score": 0.9, "source": "b.txt"},
            {"id": "c", "text": "C", "score": 0.8, "source": "c.txt"},
        ]

        candidates = rag_pipeline._retrieve_candidates("question", 2, "hybrid")

        self.assertEqual([candidate["id"] for candidate in candidates], ["a", "b", "c"])
        self.assertEqual(
            [candidate["hybrid_score"] for candidate in candidates],
            [0.5, 0.5, 0.0],
        )

    @patch("src.search.rag_pipeline.retrieve_semantic")
    @patch("src.search.rag_pipeline.retrieve_bm25")
    def test_supported_modes_dispatch_to_expected_retriever(self, bm25, semantic):
        bm25.return_value = []
        semantic.return_value = []

        rag_pipeline._retrieve_candidates("question", 4, "bm25")
        rag_pipeline._retrieve_candidates("question", 4, "SEMANTIC")

        bm25.assert_called_once_with("question", top_k=20)
        semantic.assert_called_once_with("question", top_k=20)

    @patch("src.search.rag_pipeline.ask")
    @patch("src.search.rag_pipeline.retrieve_documents")
    def test_refuses_personal_medication_and_herbal_supplement_requests(
        self, retrieve_documents, ask
    ):
        questions = (
            "Quel médicament prendre pour mes douleurs de dos à la maison ?",
            "Puis-je prendre du ginseng avec mon traitement d'amlodipine ?",
            "مريض يملك حسيسة اتجاه الاموكسيسيلين هل يمكنه شرب بيوباموكس",
        )
        for question in questions:
            answer = rag_pipeline.answer_question(question)
            self.assertTrue(
                "ne peux pas recommander" in answer
                or "يُرجى استشارة طبيب أو صيدلي" in answer
            )

        retrieve_documents.assert_not_called()
        ask.assert_not_called()


if __name__ == "__main__":
    unittest.main()
