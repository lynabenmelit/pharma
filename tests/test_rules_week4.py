import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.reasoning.medicine_rules import MedicineRules

COLS = ["subject", "subject_type", "relation", "object", "object_type",
        "source_file", "authority_level", "collected_on", "passage"]


def row(s, rel, o):
    return [s, "x", rel, o, "x", "f.txt", "3", "", f"passage {s} {o}"]


ROWS = [
    row("medicament_aspegic", "brand_of", "active_ingredient_aspirine"),
    row("medicament_adfen", "brand_of", "active_ingredient_ibuprofene"),
    row("active_ingredient_ibuprofene", "belongs_to", "therapeutic_class_ains"),
    row("active_ingredient_spironolactone",
        "belongs_to", "therapeutic_class_diur"),
    row("therapeutic_class_ains", "interacts_with:AD",
        "active_ingredient_spironolactone"),
    row("active_ingredient_aspirine", "interacts_with:PE",
        "active_ingredient_ibuprofene"),
    row("active_ingredient_aspirine", "interacts_with:CI",
        "active_ingredient_ibuprofene"),
    row("medicament_nurofen_comprime",
        "contraindicated_in", "contraindication_ulcere"),
]


class StubResolver:
    records = []

    def resolve(self, name):
        return SimpleNamespace(status="unknown", record=None)


class TestWeek4Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "triples.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLS)
            w.writerows(ROWS)
        cls.rules = MedicineRules(StubResolver(), path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_class_level_interaction(self):
        a = self.rules.check_interaction("adfen", "spironolactone")
        self.assertEqual(a.status, "found")
        self.assertTrue(a.findings[0].class_level)
        self.assertEqual(a.findings[0].level, "AD")

    def test_highest_severity_first(self):
        a = self.rules.check_interaction("aspegic", "adfen")
        self.assertEqual(a.findings[0].level, "CI")

    def test_missing_path_never_says_safe(self):
        a = self.rules.check_interaction("aspegic", "spironolactone")
        self.assertEqual(a.status, "not_found_in_sources")
        self.assertIn("Non trouvé", a.message)
        self.assertNotIn("sûr", a.message.lower())

    def test_unknown_medicine(self):
        self.assertEqual(self.rules.check_interaction("aspegic", "zzz").status,
                         "unknown_medicine")

    def test_contraindication_not_generalised(self):
        self.assertEqual(self.rules.check_contraindications(
            "nurofen").status, "found")
        self.assertEqual(self.rules.check_contraindications("nurofen sirop").status,
                         "not_found_in_sources")


if __name__ == "__main__":
    unittest.main()
