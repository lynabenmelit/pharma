import unittest
import sys
from pathlib import Path
from unittest.mock import patch

from src.search.rag_pipeline import SourceDocument

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import _grade_answer, parse_args


class EvaluationGradingTests(unittest.TestCase):
    def test_parses_a_reduced_mode_and_run_selection(self):
        with patch.object(
            sys, "argv", ["run_eval.py", "--modes", "bm25", "--runs", "1"]
        ):
            args = parse_args()

        self.assertEqual(args.modes, ["bm25"])
        self.assertEqual(args.runs, 1)

    def test_grades_facts_sources_and_every_citation_occurrence(self):
        question = {
            "id": "Q01",
            "question": "What is the fact?",
            "expected_behavior": "answer",
            "expected_sources": ["source.txt"],
            "expected_values": ["fact"],
            "expected_answer": "fact",
        }
        documents = [SourceDocument("source.txt", "fact", "source.txt")]

        result = _grade_answer(
            question,
            "bm25",
            0,
            documents,
            "The fact is stated [source.txt] [source.txt] [fake.txt].",
        )

        self.assertEqual(result["verdict"], "correct")
        self.assertEqual(result["source_hit_rate_percent"], 100.0)
        self.assertEqual(result["citation_count"], 3)
        self.assertEqual(result["valid_citation_count"], 2)
        self.assertEqual(result["invalid_citation_count"], 1)
        self.assertEqual(result["citation_valid_rate_percent"], 66.7)

    def test_grades_refusal_behavior_without_expected_fact_matching(self):
        question = {
            "id": "Q27",
            "question": "What should I take?",
            "expected_behavior": "refusal",
            "expected_sources": [],
            "expected_values": ["unused"],
            "expected_answer": "I cannot prescribe.",
        }

        result = _grade_answer(question, "semantic", 0, [], "Je ne peux pas recommander cela.")

        self.assertEqual(result["verdict"], "correct")
        self.assertEqual(result["fact_coverage_percent"], 100.0)
        self.assertEqual(result["source_hit_rate_percent"], "")

    def test_grades_arabic_personal_allergy_refusal(self):
        question = {
            "id": "Q14",
            "question": "Can this patient take the medicine?",
            "expected_behavior": "refusal",
            "expected_sources": ["amoxicilline"],
            "expected_values": [],
            "expected_answer": "Refuse a personalized recommendation.",
        }

        result = _grade_answer(
            question,
            "hybrid",
            0,
            [],
            "لا أستطيع التوصية بدواء لشخص لديه حساسية.",
        )

        self.assertEqual(result["verdict"], "correct")
        self.assertEqual(result["source_hit_rate_percent"], 0.0)


if __name__ == "__main__":
    unittest.main()
