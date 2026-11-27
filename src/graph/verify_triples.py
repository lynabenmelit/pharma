"""Automatic check of step-3 triples: an LLM judge reads each passage and says
whether it really supports (medicine, relation, object).

Usage (from repo root):
    python -m src.graph.verify_triples
"""
import argparse
import csv
import json
import re
import time
from pathlib import Path

from src.llm import ask

GRAPH = Path(__file__).resolve().parents[2] / "data" / "graph"
IN = GRAPH / "triples_step3.csv"
OK = GRAPH / "triples_step3_verified.csv"
FLAGGED = GRAPH / "triples_step3_flagged.csv"

SYSTEM = """You are a strict reviewer of medical knowledge-graph triples.
For each numbered item you get: medicine, relation, object, passage.
Answer ok=true ONLY if the passage explicitly states that:
- indicated_for: the medicine is used to treat/prevent the object;
- may_cause: the medicine can cause the object as an adverse effect;
- contraindicated_in: the medicine must NOT be used in the object situation.
Answer ok=false if the passage is about a different relation (warning, precaution,
interaction, dosage), about another drug, or if the object is vague or wrong.
Return ONLY JSON: {"verdicts":[{"id":1,"ok":true}, ...]} with one entry per item."""


def judge(batch):
    lines = [
        f'{i}. medicine={r["subject"]} | relation={r["relation"]} | '
        f'object={r["object"]} | passage="{r["passage"]}"'
        for i, r in enumerate(batch, 1)
    ]
    raw = ask("\n".join(lines), system=SYSTEM, run=0, temperature=0).strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        verdicts = json.loads(raw)["verdicts"]
        return {int(v["id"]): bool(v["ok"]) for v in verdicts}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--pause", type=float, default=2.0)
    args = ap.parse_args()

    with open(IN, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        rows = list(reader)

    ok_rows, flagged = [], []
    for start in range(0, len(rows), args.batch):
        batch = rows[start:start + args.batch]
        try:
            verdicts = judge(batch)
        except RuntimeError as e:
            print("judge failed:", e)
            verdicts = {}
        for i, row in enumerate(batch, 1):
            if verdicts.get(i) is True:
                ok_rows.append(row)
            else:
                flagged.append(row)  # no verdict counts as flagged
        time.sleep(args.pause)

    with open(OK, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(ok_rows)
    with open(FLAGGED, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(flagged)
    print(
        f"verified: {len(ok_rows)} | flagged: {len(flagged)} | total: {len(rows)}")


if __name__ == "__main__":
    main()
