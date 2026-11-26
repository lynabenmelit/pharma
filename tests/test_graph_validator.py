import csv
import tempfile
import unittest
from pathlib import Path

from src.graph.check_triples import DEFAULT_VOCABULARY, validate_triples


ROOT = Path(__file__).resolve().parents[1]
TRIPLE_COLUMNS = (
    "subject",
    "subject_type",
    "relation",
    "object",
    "object_type",
    "source_file",
    "authority_level",
    "collected_on",
    "passage",
)


class GraphTripleValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.vocabulary_path = self.root / "vocab.csv"
        self.triples_path = self.root / "triples.csv"
        self.source_path = self.root / "source.txt"
        self.source_path.write_text("A medicine and its ingredient.", encoding="utf-8")
        with self.vocabulary_path.open("w", encoding="utf-8", newline="") as vocabulary_file:
            writer = csv.writer(vocabulary_file)
            writer.writerow(("kind", "name", "domain", "range", "description"))
            writer.writerow(("entity_type", "medicament", "", "", "Medicine"))
            writer.writerow(("entity_type", "active_ingredient", "", "", "Ingredient"))
            writer.writerow(("predicate", "brand_of", "medicament", "active_ingredient", ""))
            writer.writerow(("entity", "medicament_test_brand", "medicament", "", "Test brand"))
            writer.writerow(
                ("entity", "active_ingredient_test_ingredient", "active_ingredient", "", "Test ingredient")
            )
        self.valid_row = {
            "subject": "medicament_test_brand",
            "subject_type": "medicament",
            "relation": "brand_of",
            "object": "active_ingredient_test_ingredient",
            "object_type": "active_ingredient",
            "source_file": "source.txt",
            "authority_level": "1",
            "collected_on": "",
            "passage": "A medicine and its ingredient.",
        }

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_triples(self, row=None, columns=TRIPLE_COLUMNS):
        with self.triples_path.open("w", encoding="utf-8", newline="") as triples_file:
            writer = csv.DictWriter(triples_file, fieldnames=columns)
            writer.writeheader()
            row = row or self.valid_row
            writer.writerow({column: row.get(column, "") for column in columns})

    def validate(self):
        return validate_triples(
            self.triples_path,
            self.vocabulary_path,
            source_root=self.root,
        )

    def test_sample_triples_match_the_vocabulary(self):
        sample_path = ROOT / "data" / "graph" / "triples_sample.csv"
        errors, row_count = validate_triples(sample_path, DEFAULT_VOCABULARY)

        self.assertEqual(errors, [])
        self.assertEqual(row_count, 10)

    def test_working_graph_covers_all_source_ingredients_and_attributes(self):
        triples_path = ROOT / "data" / "graph" / "triples_template.csv"
        nomenclature_path = ROOT / "data" / "medicaments_clean.csv"
        errors, _ = validate_triples(triples_path, DEFAULT_VOCABULARY)

        with triples_path.open(encoding="utf-8-sig", newline="") as triples_file:
            triples = list(csv.DictReader(triples_file))
        with nomenclature_path.open(encoding="utf-8-sig", newline="") as source_file:
            source_rows = {row["n"]: row for row in csv.DictReader(source_file)}

        ingredients = {
            row["subject"] for row in triples if row["relation"] == "has_atc"
        }
        self.assertEqual(errors, [])
        self.assertEqual(len(ingredients), 40)
        self.assertTrue(any(row["relation"] == "has_form" for row in triples))
        self.assertTrue(any(row["relation"] == "has_strength" for row in triples))

        for triple in triples:
            self.assertEqual(triple["source_file"], "data/medicaments_clean.csv")
            self.assertEqual(triple["authority_level"], "1")
            self.assertEqual(triple["collected_on"], "")
            if triple["relation"] not in {"has_form", "has_strength"}:
                continue
            self.assertTrue(
                any(
                    triple["passage"] in source_row["remarques"]
                    for source_row in source_rows.values()
                )
            )
            self.assertIn(triple["object"], triple["passage"])

    def test_rejects_an_invalid_subject_type_and_entity_id(self):
        row = dict(self.valid_row, subject_type="active_ingredient")
        self.write_triples(row)

        errors, row_count = self.validate()

        self.assertEqual(row_count, 1)
        self.assertTrue(any("expects subject type medicament" in error for error in errors))
        self.assertTrue(any("unknown subject ID" in error for error in errors))

    def test_requires_source_passage_and_valid_provenance_fields(self):
        row = dict(
            self.valid_row,
            passage="This quote is not in the source.",
            authority_level="5",
            collected_on="2026-02-30",
        )
        self.write_triples(row)

        errors, _ = self.validate()

        self.assertTrue(any("passage not found" in error for error in errors))
        self.assertTrue(any("unknown authority level" in error for error in errors))
        self.assertTrue(any("not a valid calendar date" in error for error in errors))

    def test_rejects_the_legacy_csv_contract(self):
        legacy_columns = (
            "subject",
            "subject_type",
            "predicate",
            "object",
            "object_type",
            "source",
            "source_locator",
            "evidence",
            "interaction_level",
        )
        self.write_triples(columns=legacy_columns)

        errors, row_count = self.validate()

        self.assertEqual(row_count, 0)
        self.assertTrue(any("columns must be exactly" in error for error in errors))

    def test_rejects_source_paths_outside_the_repository(self):
        row = dict(self.valid_row, source_file="..\\outside.txt")
        self.write_triples(row)

        errors, _ = self.validate()

        self.assertTrue(any("escapes the repository root" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
