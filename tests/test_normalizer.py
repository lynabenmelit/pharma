import unittest

import pandas as pd

from src.normalize.normalizer import MedicineResolver


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


if __name__ == "__main__":
    unittest.main()
