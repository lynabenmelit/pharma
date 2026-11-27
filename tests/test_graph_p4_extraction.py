import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.graph.extract_contraindications import (
    parse_response,
    select_rcp_candidates,
    triple_row,
)


class P4ContraindicationExtractionTests(unittest.TestCase):
    def test_selects_only_contraindication_candidates_from_anpp_sources(self):
        candidates = [
            {
                "topic": "contraindication",
                "source": "data/text_clean/anpp/product.txt",
            },
            {
                "topic": "indication",
                "source": "data/text_clean/anpp/product.txt",
            },
            {
                "topic": "contraindication",
                "source": "data/text_clean/anpp/combination.txt",
            },
            {
                "topic": "contraindication",
                "source": "data/text_clean/dailyMed/other-source.txt",
            },
        ]
        provenance = {
            "data/text_clean/anpp/product.txt": {
                "source": "ANPP",
                "doc_id": "anpp_example_product",
            },
            "data/text_clean/anpp/combination.txt": {
                "source": "ANPP",
                "doc_id": "example_combination",
            },
            "data/text_clean/dailyMed/other-source.txt": {"source": "DailyMed"},
        }

        with patch(
            "src.graph.extract_contraindications.COMBINATION_RCP_DOC_IDS",
            {"example_combination"},
        ):
            selected = select_rcp_candidates(candidates, provenance)

        self.assertEqual(selected, [candidates[0]])

    def test_parses_the_required_json_response_shape(self):
        payload = {
            "contraindications": [{
                "condition": "grossesse",
                "passage": "La grossesse est une contre-indication.",
            }]
        }

        self.assertEqual(
            parse_response(json.dumps(payload)),
            payload["contraindications"],
        )

    def test_rejects_non_json_llm_output(self):
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            parse_response("not json")

    def test_builds_product_to_condition_triple_with_source_verified_passage(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "rcp.txt"
            passage = "Ce médicament est contre-indiqué en cas d'hypersensibilité."
            source_path.write_text(
                "\n".join(
                    [
                        "1.1 Dénomination commerciale, dosage et forme pharmaceutique",
                        "Example Product 10 mg, Tablet",
                        "1.2 Dénomination commune internationale (DCI)",
                        "Example active ingredient",
                        passage,
                    ]
                ),
                encoding="utf-8",
            )
            source = source_path.as_posix()
            candidate = {"source": source, "evidence": passage}
            provenance = {
                source: {"authority_level": "1", "collected_on": ""}
            }

            row, reason = triple_row(
                "example ingredient",
                candidate,
                {"condition": "hypersensibilité", "passage": passage},
                provenance,
                set(),
            )

        self.assertIsNone(reason)
        self.assertEqual(row["subject"], "medicament_example_product_10_mg_tablet")
        self.assertEqual(row["relation"], "contraindicated_in")
        self.assertEqual(row["object"], "contraindication_hypersensibilite")


if __name__ == "__main__":
    unittest.main()
