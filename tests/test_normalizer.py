import unittest
from pathlib import Path

import pandas as pd

from src.normalize.normalizer import MedicineResolver, normalize_name
from src.normalizer import normalize_text
from src.reasoning.medicine_rules import MedicineRules


class MedicineResolverTests(unittest.TestCase):
    def setUp(self):
        self.resolver = MedicineResolver.from_dataframe(
            pd.DataFrame(
                [
                    {"dci": "Paracétamol", "atc": "N02BE01", "brand": "Doliprane"},
                    {"dci": "Ibuprofène", "atc": "M01AE01", "brand": "Advil"},
                ]
            )
        )

    def test_resolves_dci_brand_atc_and_typo(self):
        for query in ("paracetamol", "Doliprane", "N02BE01", "ibuprofene"):
            self.assertEqual(self.resolver.resolve(query).status, "matched")
        self.assertEqual(self.resolver.resolve("paracetmol").record.dci, "Paracétamol")

    def test_reports_unknown_and_ambiguous_results(self):
        self.assertEqual(self.resolver.resolve("not-a-medicine").status, "unknown")
        resolver = MedicineResolver.from_dataframe(
            pd.DataFrame([{"dci": "amoxicillin"}, {"dci": "amlodipine"}]),
            score_cutoff=0,
            ambiguity_margin=100,
        )
        self.assertEqual(resolver.resolve("am").status, "ambiguous")

    def test_canonical_key_includes_dose_and_form(self):
        resolver = MedicineResolver.from_dataframe(
            pd.DataFrame([{"dci": "Paracetamol", "dosage_mg": 500, "form": "Tablet"}])
        )
        self.assertEqual(resolver.records[0].canonical_key, "paracetamol|500|tablet")


class MedicineRuleTests(unittest.TestCase):
    def setUp(self):
        frame = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "medicaments_clean.csv")
        self.resolver = MedicineResolver.from_dataframe(frame)
        triples = Path(__file__).resolve().parents[1] / "data" / "graph" / "triples_p2.csv"
        self.rules = MedicineRules(self.resolver, triples)

    def test_r1_resolves_brand_and_stops_for_unknown(self):
        resolved = self.rules.resolve_brand_to_drug("Clofenal")
        self.assertEqual(resolved.status, "matched")
        self.assertEqual(normalize_name(resolved.dci), "diclofenac")

        stopped = self.rules.resolve_drug_names(["Clofenal", "invented-brand"])
        self.assertEqual(stopped[-1].status, "unknown")

    def test_r4_flags_same_dci_or_same_class(self):
        same_class = self.rules.rule_r4("diclofénac", "ibuprofène")
        self.assertTrue(same_class.same_class)
        self.assertIn("therapeutic_class_ains", same_class.shared_classes)

        same_dci = self.rules.rule_r4("diclofénac", "diclofenac")
        self.assertTrue(same_dci.same_dci)


class TextNormalizerTests(unittest.TestCase):
    def test_normalizes_accents_spaces_apostrophes_and_bold_markdown(self):
        self.assertEqual(
            normalize_text("  Pr\u00e9cautions\u00a0d’emploi **M\u00c9DICALES** "),
            "precautions d'emploi medicales",
        )


if __name__ == "__main__":
    unittest.main()
