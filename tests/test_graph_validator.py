import csv
import tempfile
import unittest
from pathlib import Path

from src.graph.check_triples import DEFAULT_VOCABULARY, validate_triples


class GraphTripleValidatorTests(unittest.TestCase):
    def test_sample_triples_match_the_vocabulary(self):
        sample_path = Path(__file__).resolve().parents[1] / "data" / "graph" / "triples_sample.csv"
        errors, row_count = validate_triples(sample_path, DEFAULT_VOCABULARY)

        self.assertEqual(errors, [])
        self.assertEqual(row_count, 10)

    def test_working_graph_covers_all_source_ingredients_and_attributes(self):
        repository_root = Path(__file__).resolve().parents[1]
        triples_path = repository_root / "data" / "graph" / "triples_template.csv"
        nomenclature_path = repository_root / "data" / "medicaments_clean.csv"
        errors, _ = validate_triples(triples_path, DEFAULT_VOCABULARY)

        with triples_path.open(encoding="utf-8-sig", newline="") as triples_file:
            triples = list(csv.DictReader(triples_file))
        with nomenclature_path.open(encoding="utf-8-sig", newline="") as source_file:
            source_rows = {
                row["n"]: row for row in csv.DictReader(source_file)
            }

        ingredients = {
            row["subject"] for row in triples if row["predicate"] == "has_ATC"
        }
        self.assertEqual(errors, [])
        self.assertEqual(len(ingredients), 40)
        self.assertTrue(any(row["predicate"] == "has_form" for row in triples))
        self.assertTrue(any(row["predicate"] == "has_strength" for row in triples))

        for triple in triples:
            if triple["predicate"] not in {"has_form", "has_strength"}:
                continue
            source_row = source_rows[triple["source_locator"].removeprefix("n=")]
            self.assertIn(triple["evidence"], source_row["remarques"])
            self.assertIn(triple["object"], triple["evidence"])

    def test_rejects_a_triple_with_the_wrong_subject_type(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            triples_path = Path(temporary_directory) / "triples.csv"
            with triples_path.open("w", encoding="utf-8", newline="") as triples_file:
                writer = csv.writer(triples_file)
                writer.writerow(
                    [
                        "subject",
                        "subject_type",
                        "predicate",
                        "object",
                        "object_type",
                        "source",
                        "source_locator",
                        "evidence",
                        "interaction_level",
                    ]
                )
                writer.writerow(
                    [
                        "paracétamol",
                        "active_ingredient",
                        "brand_of",
                        "Doliprane",
                        "medicament",
                        "test source",
                        "row 1",
                        "example evidence",
                        "",
                    ]
                )

            errors, row_count = validate_triples(triples_path, DEFAULT_VOCABULARY)

        self.assertEqual(row_count, 1)
        self.assertTrue(any("expects subject type medicament" in error for error in errors))

    def test_requires_source_and_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            triples_path = Path(temporary_directory) / "triples.csv"
            with triples_path.open("w", encoding="utf-8", newline="") as triples_file:
                writer = csv.writer(triples_file)
                writer.writerow(
                    [
                        "subject",
                        "subject_type",
                        "predicate",
                        "object",
                        "object_type",
                        "source",
                        "source_locator",
                        "evidence",
                        "interaction_level",
                    ]
                )
                writer.writerow(
                    [
                        "Doliprane",
                        "medicament",
                        "brand_of",
                        "paracétamol",
                        "active_ingredient",
                        "",
                        "",
                        "",
                        "",
                    ]
                )

            errors, _ = validate_triples(triples_path, DEFAULT_VOCABULARY)

        self.assertTrue(any("source" in error for error in errors))
        self.assertTrue(any("evidence" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
