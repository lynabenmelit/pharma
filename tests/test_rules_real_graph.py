import unittest
from pathlib import Path
from types import SimpleNamespace

from src.reasoning.medicine_rules import MedicineRules

GRAPH = Path(__file__).resolve().parents[1] / \
    "data" / "graph" / "triples_merged.csv"
ING = "active_ingredient_"
CLS = "therapeutic_class_"


class StubResolver:
    records = []

    def resolve(self, name):
        return SimpleNamespace(status="unknown", record=None)


@unittest.skipUnless(GRAPH.is_file(), "triples_merged.csv not generated")
class TestRealGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = MedicineRules(StubResolver(), GRAPH)

    def test_interaction_rows_were_loaded(self):
        self.assertTrue(self.rules.interaction_rows,
                        "no interacts_with:<LEVEL> rows loaded: check the relation format")

    def test_direct_interactions_are_found_with_their_level(self):
        for row in self.rules.interaction_rows:
            s, o = row["subject"], row["object"]
            if s.startswith(ING) and o.startswith(ING):
                a = self.rules.check_interaction(
                    s.removeprefix(ING), o.removeprefix(ING))
                self.assertEqual(a.status, "found", (s, o))
                self.assertIn(row["relation"].split(":", 1)[
                              1], {f.level for f in a.findings})

    def test_class_level_interactions_are_found(self):
        members = {}
        for ing, classes in self.rules.drug_to_classes.items():
            for c in classes:
                members.setdefault(c, []).append(ing)
        for row in self.rules.interaction_rows:
            s, o = row["subject"], row["object"]
            for cls_id, ing_id in ((s, o), (o, s)):
                if cls_id.startswith(CLS) and ing_id.startswith(ING) and cls_id in members:
                    member = members[cls_id][0]
                    a = self.rules.check_interaction(
                        member.removeprefix(ING), ing_id.removeprefix(ING))
                    self.assertEqual(a.status, "found",
                                     (member, ing_id, cls_id))

    def test_missing_path_is_not_found_never_safe(self):
        ings = sorted(
            i for i in self.rules.known_ids if i.startswith(ING))[:40]
        for i, x in enumerate(ings):
            for y in ings[i + 1:]:
                a = self.rules.check_interaction(
                    x.removeprefix(ING), y.removeprefix(ING))
                if a.status == "not_found_in_sources":
                    self.assertIn("Non trouvé", a.message)
                    self.assertNotIn("sûr", a.message.lower())
                    return
        self.skipTest("every sampled pair has an interaction")

    def test_unknown_medicine(self):
        self.assertEqual(self.rules.check_interaction("zzz_inconnu", "paracetamol").status,
                         "unknown_medicine")


if __name__ == "__main__":
    unittest.main()
