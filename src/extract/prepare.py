"""Step after extractor.py: clean + filter the text files in data/text/.

Reads   data/text/<source>/*.txt     (source = dailyMed, anpp, ... same layout as data/raw/)
        data/provenance.csv          (optional; missing cells are filled automatically)
Writes  data/text_clean/<source>/*.txt
        data/clean_docs.csv          metadata + quality flags + doses in mg
        data/rejected.csv            dropped docs + reason
        reports/week1_prep_report.json

Run from the project root:   python src/extract/prepare.py
"""
import csv
import hashlib
import json
import re
import statistics
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import prep_config as config
from src.normalize.units import extract_doses, norm_name

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "œ": "oe", "’": "'", "‘": "'",
             "«": '"', "»": '"', "–": "-", "—": "-", " ": " ", " ": " "}
FR = {"le", "la", "les", "des", "de", "du", "et", "est", "pour", "dans", "chez", "une"}
EN = {"the", "of", "and", "is", "for", "with", "in", "to", "patients", "use"}


# ---------- cleaning ----------
def clean_text(t: str) -> str:
    t = unicodedata.normalize("NFC", t)
    for a, b in LIGATURES.items():
        t = t.replace(a, b)
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", t)
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)                  # re-join hyphenated words
    t = re.sub(r"https?://\S+|www\.\S+", "", t)
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n")]
    counts = {}
    for l in lines:
        if l and len(l) < 80:
            counts[l] = counts.get(l, 0) + 1
    lines = [l for l in lines if not (l and len(l) < 80 and counts[l] >= 3)]  # headers/footers
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def garbage_ratio(t: str) -> float:
    if not t:
        return 1.0
    ok = sum(c.isalnum() or c.isspace() or c in ".,;:()%/+-'\"°µ" for c in t)
    return 1 - ok / len(t)


def detect_lang(t: str) -> str:
    if re.search(r"[؀-ۿ]", t[:2000]):
        return "ar"
    w = re.findall(r"[a-zàâçéèêëîïôûùüÿ]+", t.lower()[:5000])
    return "fr" if sum(x in FR for x in w) >= sum(x in EN for x in w) else "en"


def dose_outliers(doses, cap=config.MAX_DOSE_MG):
    mg = [v for v, u in doses if u == "mg"]
    if len(mg) >= 8:
        med = statistics.median(mg)
        mad = statistics.median(abs(x - med) for x in mg) or 1.0
        return [x for x in mg if abs(x - med) / mad > 10]
    return [x for x in mg if x > cap or x <= 0]


def length_outliers(lengths: dict):
    if len(lengths) < 4:
        return {}
    q1, _, q3 = statistics.quantiles(lengths.values(), n=4, method="inclusive")
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    return {k: v < lo or v > hi for k, v in lengths.items()}


# ---------- provenance (tolerant to column names) ----------
def load_provenance(path: Path):
    """Return {file_stem: row} ; keys are lower-cased column names."""
    out = {}
    if not path.exists():
        return out
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
            for k, v in r.items():
                if v and any(w in k for w in ("path", "file", "local", "text", "raw")):
                    out[Path(v.replace("\\", "/")).stem] = r
    return out


def pick(row: dict, *keys):
    for k in row:
        if any(w in k for w in keys) and row[k]:
            return row[k]
    return ""


# ---------- pipeline ----------
def run(text_dir=config.TEXT, out_dir=config.TEXT_CLEAN, provenance=config.PROVENANCE,
        clean_csv=config.CLEAN_DOCS_CSV, rejected_csv=config.REJECTED_CSV,
        report_dir=config.REPORTS):
    text_dir, out_dir, report_dir = Path(text_dir), Path(out_dir), Path(report_dir)
    prov = load_provenance(Path(provenance))
    kept, rejected, seen = [], [], {}

    for p in sorted(text_dir.rglob("*.txt")):
        rel = p.relative_to(text_dir)
        folder = rel.parts[0].lower() if len(rel.parts) > 1 else "unknown"
        m = prov.get(p.stem, {})
        text = clean_text(p.read_text(encoding="utf-8", errors="ignore"))

        # missing values in metadata -> fill
        lang = pick(m, "lang") or detect_lang(text)
        auth = pick(m, "authority", "autorit") or config.AUTHORITY.get(folder, config.DEFAULT_AUTHORITY)
        collected = pick(m, "date", "collected") or date.fromtimestamp(p.stat().st_mtime).isoformat()
        drug = pick(m, "drug", "dci", "medic") or p.stem.split("_")[0]

        # filtering
        reason = None
        if len(text) < config.MIN_CHARS:
            reason = "too_short"
        elif garbage_ratio(text) > config.MAX_GARBAGE:
            reason = "ocr_garbage"
        else:
            h = hashlib.md5(re.sub(r"\W+", "", text.lower()).encode()).hexdigest()
            if h in seen:
                reason = f"duplicate_of:{seen[h]}"
            else:
                seen[h] = str(rel)
        if reason:
            rejected.append({"file": str(rel), "reason": reason})
            continue

        doses = extract_doses(text)
        (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (out_dir / rel).write_text(text, encoding="utf-8")
        kept.append({"file": str(rel), "source": folder, "drug": drug, "drug_norm": norm_name(drug),
                     "url": pick(m, "url"), "date": collected, "language": lang, "authority": auth,
                     "n_chars": len(text), "garbage": round(garbage_ratio(text), 4),
                     "n_doses": len(doses),
                     "dose_outliers_mg": ";".join(map(str, dose_outliers(doses))),
                     "doses": ";".join(f"{v}{u}" for v, u in doses[:50])})

    flags = length_outliers({r["file"]: r["n_chars"] for r in kept})
    for r in kept:
        r["length_outlier"] = int(flags.get(r["file"], False))   # flagged for review, not deleted

    if kept:
        with open(clean_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(kept[0])); w.writeheader(); w.writerows(kept)
    with open(rejected_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "reason"]); w.writeheader(); w.writerows(rejected)

    rep = {"input_docs": len(kept) + len(rejected), "kept": len(kept), "rejected": len(rejected),
           "rejected_by_reason": {k: sum(r["reason"].startswith(k) for r in rejected)
                                  for k in ("too_short", "ocr_garbage", "duplicate_of")},
           "length_outliers_flagged": sum(r["length_outlier"] for r in kept),
           "docs_with_dose_outliers": sum(bool(r["dose_outliers_mg"]) for r in kept),
           "docs_per_source": {s: sum(r["source"] == s for r in kept) for s in {r["source"] for r in kept}}}
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "week1_prep_report.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return rep


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
