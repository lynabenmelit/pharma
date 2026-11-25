import tempfile
import unittest
from pathlib import Path

from src.reconcile.provenance import reconcile


class ReconciliationTests(unittest.TestCase):
    def test_reports_missing_registry_and_clean_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provenance = root / "provenance.csv"
            clean = root / "clean.csv"
            rejected = root / "rejected.csv"
            text = root / "text_clean"
            text.mkdir()
            (text / "b.txt").write_text("b", encoding="utf-8")

            provenance.write_text(
                "text_path\nfolder/a.txt\nfolder/b.txt\n",
                encoding="utf-8",
            )
            clean.write_text("file\nfolder/a.txt\nfolder/c.txt\n", encoding="utf-8")
            rejected.write_text(
                "file,reason\nfolder/d.txt,too_short\n",
                encoding="utf-8",
            )

            result = reconcile(provenance, clean, text, rejected)

            self.assertEqual(result["accepted_without_provenance"], ["c.txt"])
            self.assertEqual(
                result["provenance_without_accepted_document"], ["b.txt"]
            )
            self.assertEqual(
                result["row_counts"],
                {
                    "provenance_collected": 2,
                    "accepted_clean_docs": 2,
                    "rejected": 1,
                },
            )


if __name__ == "__main__":
    unittest.main()
