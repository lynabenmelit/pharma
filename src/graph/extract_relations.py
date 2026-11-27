"""Step 3: extract medicament -> indication / adverse effect / contraindication
triples from the chunk corpus, each justified by a verbatim passage.

Writes (all in data/graph/):
  triples_step3.csv             validated-format triples
  triples_step3_rejected.csv    rejected candidates with a reason
  vocab_step3_additions.csv     new entities, same format as vocab.csv
  vocab_step3_merged.csv        vocab.csv + additions (for validation)

Usage (from repo root):
    python -m src.graph.extract_relations --limit 20
    python -m src.graph.extract_relations
    python -m src.graph.extract_relations --drug amlodipine
"""
import argparse
import csv
import io
import json
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

from src.llm import ask

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "data" / "graph"
CHUNKS = ROOT / "data" / "chunks.jsonl"
PROVENANCE = ROOT / "data" / "provenance.csv"
VOCAB = GRAPH / "vocab.csv"
OUT = GRAPH / "triples_step3.csv"
REJECTED = GRAPH / "triples_step3_rejected.csv"
ADDITIONS = GRAPH / "vocab_step3_additions.csv"
MERGED = GRAPH / "vocab_step3_merged.csv"

COLUMNS = [
    "subject", "subject_type", "relation", "object", "object_type",
    "source_file", "authority_level", "collected_on", "passage",
]
VOCAB_COLUMNS = ["kind", "name", "domain", "range", "description"]

RELATIONS = {
    "indicated_for": "indication",
    "may_cause": "adverse_effect",
    "contraindicated_in": "contraindication",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CUES = re.compile(
    r"indication|indiqu|traitement de|contre-indic|contraindic|ne prenez jamais|"
    r"ne pas utiliser|effets? ind[ée]sirables?|adverse (reaction|effect)|"
    r"side effects?|hypersensib|hypersensitiv|is indicated|used (for|to treat)",
    re.I,
)

SYSTEM = """You extract medical relations from a drug leaflet excerpt.

Allowed relations:
- indicated_for: the medicine is used to treat or prevent the object
  (a disease or symptom). Use only text about indications.
- may_cause: the medicine may cause the object (an adverse effect).
  Use only lists of adverse / undesirable effects.
- contraindicated_in: the medicine must not be used in the object.
  Use only text about contraindications ("ne prenez jamais", "contre-indique").

Rules:
- Use only what the text explicitly states about the given medicine.
- NEVER output another drug, a substance (alcohol), a drug class or a dose as an
  object. Drug interactions and associations are NOT contraindications here.
- Warnings and precautions are not contraindications. Do not output them.
- "object": ONE generic concept, 1-4 words, in the language of the text,
  lowercase, singular, no numbers, no doses, no durations, no parentheses.
  Pregnancy of any stage or duration -> "grossesse". Do not output several
  variants of the same concept; keep only the most general term.
- "passage": ONE sentence or fragment (max 300 characters) copied EXACTLY,
  character for character, from the excerpt, which states the relation.
- At most 15 relations. If nothing qualifies, return {"relations": []}.

Return ONLY JSON:
{"relations":[{"relation":"...","object":"...","passage":"..."}]}"""


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode(
        "ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def canon(text: str) -> str:
    """slug with a light singularisation, so crises/crise or nausees/nausee merge."""
    tokens = []
    for tok in slug(text).split("_"):
        if len(tok) > 4 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
            tok = tok[:-1]
        tokens.append(tok)
    return "_".join(t for t in tokens if t)


def norm_ws(text: str) -> str:
    # Same normalisation as check_triples.py (whitespace only, case-sensitive)
    return re.sub(r"\s+", " ", text).strip()


def load_vocab():
    """-> (existing entity ids, slugs of active ingredient labels, raw vocab text)"""
    ids, ingredient_slugs = set(), set()
    raw = VOCAB.read_text(encoding="utf-8-sig")
    for row in csv.DictReader(io.StringIO(raw)):
        if (row.get("kind") or "").strip() == "entity":
            ids.add(row["name"].strip())
            if (row.get("domain") or "").strip() == "active_ingredient":
                ingredient_slugs.add(slug(row.get("description") or ""))
    return ids, ingredient_slugs, raw


def load_chunks():
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def load_provenance():
    """file stem -> (authority_level, collected_on)"""
    info = {}
    if PROVENANCE.exists():
        with open(PROVENANCE, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                for key in ("text_path", "raw_path"):
                    p = (row.get(key) or "").strip()
                    if p:
                        info[Path(p.replace("\\", "/")).stem] = (
                            row.get("authority_level", ""),
                            row.get("collected_on", ""),
                        )
    return info


def extract(drug: str, text: str) -> list:
    """One LLM call through src/llm.py (shared retries and cache)."""
    raw = ask(
        f"Medicine: {drug}\n\nExcerpt:\n{text}",
        system=SYSTEM, run=0, temperature=0,
    ).strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        rels = json.loads(raw).get("relations", [])
        return rels if isinstance(rels, list) else []
    except (json.JSONDecodeError, AttributeError):
        return []


_source_cache = {}


def source_text(rel_path: str) -> str:
    if rel_path not in _source_cache:
        p = ROOT / rel_path
        _source_cache[rel_path] = (
            norm_ws(p.read_text(encoding="utf-8-sig", errors="replace"))
            if p.is_file() else ""
        )
    return _source_cache[rel_path]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="max chunks to send to the LLM")
    ap.add_argument("--drug", default="",
                    help="only chunks whose drug contains this")
    ap.add_argument("--pause", type=float, default=2.0)
    ap.add_argument("--max-chunks-per-drug", type=int, default=5,
                    help="0 = no cap")
    ap.add_argument("--max-per-relation", type=int, default=8,
                    help="max triples per medicine and relation, 0 = no cap")
    args = ap.parse_args()

    known_ids, ingredient_slugs, vocab_raw = load_vocab()
    prov = load_provenance()
    GRAPH.mkdir(parents=True, exist_ok=True)

    new_entities = {}          # id -> (entity type, label)
    seen, kept, rejected = set(), [], []
    chunks_per_drug, per_relation = Counter(), Counter()
    processed = skipped_cap = 0

    for ch in load_chunks():
        drug = (ch.get("drug") or "").strip()
        if not drug or not CUES.search(ch["text"]):
            continue
        if args.drug and args.drug.lower() not in (
            drug + " " + ch.get("drug_norm", "")
        ).lower():
            continue
        if args.max_chunks_per_drug and chunks_per_drug[drug] >= args.max_chunks_per_drug:
            continue
        if args.limit and processed >= args.limit:
            break
        processed += 1
        chunks_per_drug[drug] += 1

        src = ch["document_path"].replace("\\", "/")
        try:
            rels = extract(drug, ch["text"])
        except RuntimeError as e:
            print("chunk", ch["chunk_id"], "failed:", e)
            if "429" in str(e) or "Quota" in str(e):
                print("Quota hit: stopping. Rerun later; finished chunks are cached.")
                break
            continue
        time.sleep(args.pause)

        auth, date = prov.get(Path(src).stem, (ch.get("authority", ""), ""))
        auth = str(auth).strip()
        date = (date or "").strip()
        if not DATE_RE.fullmatch(date):
            date = ""

        subject_id = f"medicament_{slug(drug)}"
        for r in rels:
            if not isinstance(r, dict):
                continue
            rel = r.get("relation", "")
            obj = (r.get("object") or "").strip()
            passage = (r.get("passage") or "").strip()
            obj_type = RELATIONS.get(rel, "")
            obj_slug = canon(obj)
            object_id = f"{obj_type}_{obj_slug}" if obj_type and obj_slug else ""
            row = dict(zip(COLUMNS, [
                subject_id, "medicament", rel, object_id, obj_type,
                src, auth, date, passage,
            ]))

            reason = None
            if rel not in RELATIONS or not obj_slug or not passage:
                reason = "bad_relation_or_empty"
            elif re.search(r"\d", obj):
                reason = "numeric_object"
            elif obj_slug in ingredient_slugs or obj_slug == slug(drug):
                reason = "object_is_a_drug"
            elif auth not in {"1", "2", "3", "4"}:
                reason = "bad_authority_level"
            elif norm_ws(passage) not in source_text(src):
                reason = "passage_not_in_source"
            if reason:
                rejected.append({**row, "reason": reason})
                continue

            key = (subject_id, rel, object_id, src)
            if key in seen:
                continue
            if args.max_per_relation and per_relation[(subject_id, rel)] >= args.max_per_relation:
                skipped_cap += 1
                continue
            seen.add(key)
            per_relation[(subject_id, rel)] += 1
            kept.append(row)

            for ent_id, ent_type, label in (
                (subject_id, "medicament", drug),
                (object_id, obj_type, obj),
            ):
                if ent_id not in known_ids and ent_id not in new_entities:
                    new_entities[ent_id] = (ent_type, label)

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(kept)
    with open(REJECTED, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS + ["reason"])
        w.writeheader()
        w.writerows(rejected)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for ent_id, (ent_type, label) in sorted(new_entities.items()):
        writer.writerow(["entity", ent_id, ent_type, "", label])
    with open(ADDITIONS, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(VOCAB_COLUMNS) + "\n" + buf.getvalue())
    with open(MERGED, "w", encoding="utf-8", newline="") as f:
        f.write(vocab_raw.replace("\r\n", "\n").rstrip(
            "\n") + "\n" + buf.getvalue())

    print(f"chunks processed: {processed} | kept: {len(kept)} | "
          f"rejected: {len(rejected)} | skipped (cap): {skipped_cap} | "
          f"new vocab entities: {len(new_entities)}")


if __name__ == "__main__":
    main()
