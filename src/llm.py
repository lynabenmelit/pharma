import os, json, time, hashlib, requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
CACHE_FILE = BASE_DIR / "cache" / "llm_cache.json"


def _load():
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def ask(prompt, system="Tu es un assistant précis.", run=0, temperature=0.3):
    cache = _load()
    key = hashlib.sha256(
        f"{MODEL}|{system}|{prompt}|{run}|{temperature}".encode()
    ).hexdigest()
    if key in cache:
        return cache[key]
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY manquante dans .env")
    for _ in range(3):
        r = requests.post(
            URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": MODEL, "temperature": temperature,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": prompt}]},
            timeout=60)
        if r.status_code == 429:
            time.sleep(10)
            continue
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"]
        cache[key] = answer
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        return answer
    raise RuntimeError("Quota / 429 : prevenir l'enseignant")


if __name__ == "__main__":
    print(ask("Réponds juste : OK"))