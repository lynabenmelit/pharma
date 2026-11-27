import os, json, time, hashlib, requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
CACHE_FILE = BASE_DIR / "cache" / "llm_cache.json"
RETRY_WAIT_BUDGET_SECONDS = 60


def _load():
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def ask(prompt, system="Tu es un assistant précis.", run=0, temperature=0.3,
        usage=None):
    cache = _load()
    key = hashlib.sha256(
        f"{MODEL}|{system}|{prompt}|{run}|{temperature}".encode()
    ).hexdigest()
    if key in cache:
        if usage is not None:
            usage["cache_hits"] = usage.get("cache_hits", 0) + 1
        return cache[key]
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY manquante dans .env")
    attempts = 5
    retry_waited = 0.0
    for attempt in range(attempts):
        if usage is not None:
            usage["api_requests"] = usage.get("api_requests", 0) + 1
        try:
            r = requests.post(
                URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": MODEL, "temperature": temperature,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": prompt}]},
                timeout=60)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
            if attempt == attempts - 1:
                raise RuntimeError(
                    f"Groq request failed after {attempts} network attempts"
                ) from error
            time.sleep(min(10 * (2 ** attempt), 60))
            continue

        if r.status_code == 429 or r.status_code >= 500:
            if attempt == attempts - 1:
                if r.status_code == 429:
                    raise RuntimeError("Quota / 429 : prevenir l'enseignant")
                r.raise_for_status()
            retry_after = r.headers.get("Retry-After")
            try:
                delay = max(0.0, float(retry_after))
            except (TypeError, ValueError):
                delay = min(10 * (2 ** attempt), 60)
            if retry_waited + delay > RETRY_WAIT_BUDGET_SECONDS:
                raise RuntimeError(
                    f"Groq returned HTTP {r.status_code} and requested a "
                    f"{delay:g}s retry delay (Retry-After: "
                    f"{retry_after or 'not provided'}), exceeding the "
                    f"{RETRY_WAIT_BUDGET_SECONDS}s automatic retry-wait budget. "
                    "Wait for the quota to reset, then rerun the evaluation; "
                    "completed answers are checkpointed."
                )
            print(
                f"Groq returned HTTP {r.status_code}; retrying in {delay:g}s "
                f"(attempt {attempt + 2}/{attempts}).",
                flush=True,
            )
            time.sleep(delay)
            retry_waited += delay
            continue

        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"]
        cache[key] = answer
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        if usage is not None:
            usage["successful_responses"] = (
                usage.get("successful_responses", 0) + 1
            )
        return answer
    raise RuntimeError("Groq request failed after all retry attempts")


if __name__ == "__main__":
    print(ask("Réponds juste : OK"))