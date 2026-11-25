import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from src import llm


class LLMRetryTests(unittest.TestCase):
    def test_retries_connection_failure_and_caches_success(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }
        response.headers = {}

        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "llm_cache.json"
            with (
                patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}),
                patch.object(llm, "CACHE_FILE", cache_path),
                patch(
                    "src.llm.requests.post",
                    side_effect=[
                        requests.exceptions.ConnectionError("reset"),
                        response,
                    ],
                ) as post,
                patch("src.llm.time.sleep") as sleep,
            ):
                self.assertEqual(llm.ask("test prompt"), "OK")
                self.assertEqual(llm.ask("test prompt"), "OK")

        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(10)

    def test_stops_instead_of_waiting_for_long_retry_after(self):
        response = Mock()
        response.status_code = 429
        response.headers = {"Retry-After": "900"}

        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "llm_cache.json"
            with (
                patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}),
                patch.object(llm, "CACHE_FILE", cache_path),
                patch("src.llm.requests.post", return_value=response) as post,
                patch("src.llm.time.sleep") as sleep,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "Retry-After: 900"
                ):
                    llm.ask("test prompt")

        post.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
