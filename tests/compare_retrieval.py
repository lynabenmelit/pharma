"""P4 -- Compare BM25 vs semantic retrieval on tests/test_questions.json.

Usage (from the repository root):

    python tests\\compare_retrieval.py
    python tests\\compare_retrieval.py --top-k 5

For each question it records: BM25 passages, semantic passages, which expected
facts appear in the retrieved text, and a coverage score (found / expected).
Refusal questions and questions without expected values are not scored.

Optional: add a "retrieval_values" list to a question in the JSON to override
"expected_values" for retrieval scoring (useful when expected_values contains
words that belong to the answer, not to the source documents).

Output: reports/compare_retrieval_results.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "search"))
from bm25 import retrieve_bm25  # noqa: E402
from semantic import retrieve_semantic  # noqa: E402

QUESTIONS = ROOT / "tests" / "test_questions.json"
OUT_FILE = ROOT / "reports" / "compare_retrieval_results.csv"
REFUSAL = {"refuse", "refusal"}


def norm(text: str) -> str:
    """Lowercase, strip accents, unify apostrophes and decimal commas."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("’", "'")
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)  # 7,5 -> 7.5
    return re.sub(r"\s+", " ", text).strip()


def contains(blob: str, fact: str) -> bool:
    """Whole-token match; '5 mg' must not match '15 mg' or '7.5 mg'."""
    pattern = re.escape(norm(fact)).replace(r"\ ", r"\s*")
    return re.search(rf"(?<![\w.,]){pattern}(?![\w])", blob) is not None


def coverage(passages: list[dict], facts: list[str]) -> tuple[list[str], float]:
    blob = norm(" ".join(p["text"] for p in passages))
    found = [f for f in facts if contains(blob, f)]
    return found, len(found) / len(facts)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--out", type=Path, default=OUT_FILE)
    args = parser.parse_args()

    data = json.loads(args.questions.read_text(encoding="utf-8"))
    questions = data["questions"] if isinstance(data, dict) else data

    rows = []
    for q in questions:
        facts = q.get("retrieval_values") or q.get("expected_values") or []
        scored = q.get("expected_behavior") not in REFUSAL and bool(facts)

        bm = retrieve_bm25(q["question"], args.top_k)
        se = retrieve_semantic(q["question"], args.top_k)

        row = {
            "id": q["id"],
            "category": q.get("category", ""),
            "question": q["question"].strip(),
            "scored": scored,
            "expected_facts": ";".join(facts),
            "bm25_passages": ";".join(p["id"] for p in bm),
            "semantic_passages": ";".join(p["id"] for p in se),
            "bm25_found": None, "semantic_found": None,
            "bm25_coverage": None, "semantic_coverage": None,
            "winner": "n/a",
        }
        if scored:
            bm_found, bm_cov = coverage(bm, facts)
            se_found, se_cov = coverage(se, facts)
            row.update(
                bm25_found=";".join(bm_found),
                semantic_found=";".join(se_found),
                bm25_coverage=round(bm_cov, 2),
                semantic_coverage=round(se_cov, 2),
                winner="bm25" if bm_cov > se_cov else "semantic" if se_cov > bm_cov else "tie",
            )
        rows.append(row)
        print(
            f"{row['id']}  bm25={row['bm25_coverage']}  semantic={row['semantic_coverage']}  -> {row['winner']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    scored_rows = [r for r in rows if r["scored"]]
    print(
        f"\n=== Summary (top_k={args.top_k}, {len(scored_rows)} scored of {len(rows)} questions) ===")
    print(f"Mean coverage  BM25: {mean([r['bm25_coverage'] for r in scored_rows]):.2f}   "
          f"Semantic: {mean([r['semantic_coverage'] for r in scored_rows]):.2f}")
    for w in ("bm25", "semantic", "tie"):
        print(f"  {w}: {sum(r['winner'] == w for r in scored_rows)} questions")
    by_cat = defaultdict(list)
    for r in scored_rows:
        by_cat[r["category"]].append(r)
    print("By category (BM25 / semantic):")
    for cat, rs in sorted(by_cat.items()):
        print(f"  {cat:<16} {mean([r['bm25_coverage'] for r in rs]):.2f} / "
              f"{mean([r['semantic_coverage'] for r in rs]):.2f}  (n={len(rs)})")
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
