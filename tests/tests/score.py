import csv
from pathlib import Path

path = Path(__file__).resolve().parent / "results_week1.csv"
points = {"correct": 1, "partial": 0.5, "wrong": 0}

with open(path, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f, delimiter=";"))

by_run = {}
for r in rows:
    v = r["verdict"].strip().lower()
    if v in points:
        by_run.setdefault(r["run"], []).append(points[v])

if not by_run:
    raise SystemExit("No verdicts filled in yet.")

for run, pts in sorted(by_run.items()):
    print(f"Run {run}: {sum(pts)}/{len(pts)} = {sum(pts)/len(pts):.0%}")

all_pts = [p for pts in by_run.values() for p in pts]
print(f"Average: {sum(all_pts)/len(all_pts):.0%}")