import unittest

from src.search.rag_pipeline import SourceDocument
from src.verify.citations import verify_citations


class CitationTests(unittest.TestCase):
    def test_accepts_only_retrieved_source_titles(self):
        documents = [
            SourceDocument("a.txt", "A", "data/text_clean/a.txt"),
            SourceDocument("b.txt", "B", "data/text_clean/b.txt"),
        ]

        result = verify_citations("Selon [a.txt] puis [fake.txt].", documents)

        self.assertEqual(result["verified"], ["a.txt"])
        self.assertEqual(result["unsupported"], ["fake.txt"])

    def test_counts_repeated_citations_as_separate_occurrences(self):
        document = SourceDocument("a.txt", "A", "data/text_clean/a.txt")

        result = verify_citations("[a.txt] and [a.txt] and [missing.txt].", [document])

        self.assertEqual(result["cited"], ["a.txt", "a.txt", "missing.txt"])
        self.assertEqual(result["verified"], ["a.txt", "a.txt"])
        self.assertEqual(result["unsupported"], ["missing.txt"])

    def test_extracts_full_width_citation_brackets(self):
        document = SourceDocument("a.txt", "A", "data/text_clean/a.txt")

        result = verify_citations("According to 【a.txt】 and 【fake.txt】.", [document])

        self.assertEqual(result["cited"], ["a.txt", "fake.txt"])
        self.assertEqual(result["verified"], ["a.txt"])
        self.assertEqual(result["unsupported"], ["fake.txt"])


if __name__ == "__main__":
    unittest.main()
