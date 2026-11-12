import csv, hashlib
from pathlib import Path

CSV = Path("data/provenance.csv")
rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
cols = list(rows[0].keys())
for c in ("sha256", "terms_checked", "remarks"):
    if c not in cols:
        cols.append(c)

for r in rows:
    p = Path(r["raw_path"])
    if not p.exists():
        found = list(Path("data/raw").rglob(p.name))
        if found:
            p = found[0]
            r["raw_path"] = p.as_posix()
    r["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "FILE NOT FOUND"
    r["terms_checked"] = r.get("terms_checked") or ""
    r["remarks"] = r.get("remarks") or ""
    print(r["doc_id"], "->", r["sha256"][:12], "|", r["raw_path"])

with open(CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)