import unittest
import tempfile
from pathlib import Path

from src.graph.extract_evidence_candidates import (
    extract_sections,
    source_contains_evidence,
)


class EvidenceCandidateExtractionTests(unittest.TestCase):
    def test_extracts_supported_french_sections_until_the_next_numbered_heading(self):
        text = (
            "4.1. Indications thérapeutiques :\n"
            "Traitement de la douleur légère à modérée.\n\n"
            "4.2. Posologie :\n"
            "Prendre selon la notice.\n\n"
            "4.2- Posologie et mode d'administration\n"
            "Un paragraphe de posologie à ne pas classer comme indication.\n\n"
            "4.3. Contre-indications :\n"
            "Hypersensibilité à la substance active.\n\n"
            "4.4. Mises en garde :\n"
            "Texte non concerné par cette extraction."
        )

        sections = extract_sections(text)

        self.assertEqual([section[0] for section in sections], ["indication", "contraindication"])
        self.assertEqual(
            sections[0][2],
            ["Traitement de la douleur légère à modérée."],
        )
        self.assertEqual(
            sections[1][2],
            ["Hypersensibilité à la substance active."],
        )

    def test_extracts_daily_med_style_headings(self):
        text = (
            "INDICATIONS AND USAGE\n"
            "For treatment of the condition described in the label.\n\n"
            "DOSAGE AND ADMINISTRATION\n"
            "Use the dosage in the label."
        )

        sections = extract_sections(text)

        self.assertEqual([section[0] for section in sections], ["indication"])

    def test_confirms_evidence_when_source_has_different_line_wrapping(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "source.txt"
            source_path.write_text(
                "Traitement de la douleur\nlégère à modérée.",
                encoding="utf-8",
            )

            self.assertTrue(
                source_contains_evidence(
                    source_path,
                    "Traitement de la douleur légère à modérée.",
                )
            )


if __name__ == "__main__":
    unittest.main()
