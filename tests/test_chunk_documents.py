import unittest

from src.search.chunk_documents import chunk_text


class ChunkDocumentsTests(unittest.TestCase):
    def test_creates_bounded_chunks(self):
        text = ("Premiere section. " * 100) + "\n\n" + ("Deuxieme section. " * 100)
        chunks = chunk_text(text, max_chars=500, overlap_chars=100)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))

    def test_empty_text_returns_no_chunks(self):
        self.assertEqual(chunk_text("  \n\n "), [])

    def test_rejects_invalid_overlap(self):
        with self.assertRaises(ValueError):
            chunk_text("texte", max_chars=100, overlap_chars=100)



if __name__ == "__main__":
    unittest.main()
