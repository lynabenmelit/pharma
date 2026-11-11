import os
import json
import time
import hashlib
import requests
from pathlib import Path
from dotenv import load_dotenv

# Automatically locate the root project directory (one level up from src/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the root directory
load_dotenv(BASE_DIR / ".env")

URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
CACHE_FILE = BASE_DIR / "cache" / "llm_cache.json"


def _load():
    try:
        if CACHE_FILE.exists():
            data = json.load(open(CACHE_FILE, encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def ask(prompt, system="Tu es un assistant précis."):
    cache = _load()
    key = hashlib.sha256((MODEL + system + prompt).encode()).hexdigest()
    if key in cache:
        return cache[key]
    for _ in range(3):
        r = requests.post(
            URL,
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            json={"model": MODEL, "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}]},
            timeout=60)
        if r.status_code == 429:
            time.sleep(10)
            continue
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"]
        cache[key] = answer

        # Ensure the cache directory exists before writing
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        json.dump(cache, open(CACHE_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False)
        return answer
    raise RuntimeError("Quota / 429 : prevenir l'enseignant")


if __name__ == "__main__":
    print(ask("Réponds juste : OK"))
