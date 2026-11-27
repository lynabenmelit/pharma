"""Extract product-to-condition contraindications from ANPP product information."""
import argparse
import csv
import io
import json
import re
import time
from pathlib import Path

from src.graph.extract_evidence_candidates import (
    ROOT,
    clinical_candidates,
    normalize_heading,
    normalize_whitespace,
    source_contains_evidence,
)
from src.graph.extract_relations import COLUMNS, VOCAB_COLUMNS, canon, load_vocab, slug
from src.llm import ask


GRAPH = ROOT / "data" / "graph"
PROVENANCE = ROOT / "data" / "provenance.csv"
OUTPUT = GRAPH / "triples_p4.csv"
REJECTED = GRAPH / "triples_p4_rejected.csv"
VOCAB_ADDITIONS = GRAPH / "vocab_p4_additions.csv"
MERGED_VOCAB = GRAPH / "vocab_p4_merged.csv"
REJECTED_COLUMNS = COLUMNS + ["reason", "source_locator"]
# These combination-product labels cannot safely inherit a single-DCI subject.
COMBINATION_RCP_DOC_IDS = {
    "anpp_paracetamol_panadol_extra",
    "anpp_paracetamol_rynza",
    "anpp_paracetamol_xamadol",
}

SYSTEM = """Extract only explicit drug-to-condition contraindications from the
provided medicine product-information excerpt.

Return ONLY JSON in this exact shape:
{"contraindications":[{"condition":"...","passage":"..."}]}

Rules:
- Include a condition only when the text explicitly says this medicine must
  not be used in that situation. Do not infer a contraindication from risk,
  warning, monitoring advice, or precaution.
- Return medical conditions or situations, not another medicine, drug class,
  dose, or interaction. Drug-drug interactions are out of scope.
- Return one generic condition per item, in the language of the source.
  Remove age, dose, and duration qualifiers from the condition label, but keep
  them in the quoted passage. Do not invent a condition.
- "passage" must be copied exactly from the provided excerpt and must support
  that condition. Return an empty list when no contraindication is explicit.
"""

USER_PROMPT = """Medicine: {drug}
Source excerpt:
{evidence}
"""


def load_provenance() -> dict[str, dict[str, str]]:
    provenance = {}
    with PROVENANCE.open(encoding="utf-8-sig", newline="") as source_file:
        for row in csv.DictReader(source_file):
            source_path = (row.get("text_path") or "").replace("\\", "/")
            prefix = "data/text/"
            if not source_path.startswith(prefix):
                continue
            clean_path = "data/text_clean/" + source_path[len(prefix):]
            provenance[clean_path] = row
    return provenance


def select_rcp_candidates(candidates, provenance):
    return [
        candidate
        for candidate in candidates
        if candidate.get("topic") == "contraindication"
        and provenance.get(candidate.get("source", ""), {}).get(
            "source", ""
        ).casefold() == "anpp"
        and provenance.get(candidate.get("source", ""), {}).get(
            "doc_id", ""
        ) not in COMBINATION_RCP_DOC_IDS
    ]


def product_name_from_rcp(source_path: Path) -> str:
    try:
        text = source_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = source_path.read_text(encoding="cp1252")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        heading = normalize_heading(line)
        if (
            "denomination commerciale" in heading
            and "forme pharmaceutique" in heading
        ):
            inline_name = line.split(":", 1)[1].strip() if ":" in line else ""
            if inline_name:
                return normalize_whitespace(inline_name).strip(" .")
            for candidate_line in lines[index + 1:]:
                candidate_line = candidate_line.strip()
                if not candidate_line:
                    continue
                if re.match(r"^\d+(?:\.\d+)*\b", candidate_line):
                    break
                return normalize_whitespace(candidate_line).strip(" .")
        elif heading in {"denomination", "denomination du medicament"}:
            for candidate_line in lines[index + 1:]:
                candidate_line = candidate_line.strip()
                if not candidate_line:
                    continue
                if re.match(r"^\d+(?:\.\d+)*\b", candidate_line):
                    break
                return normalize_whitespace(candidate_line).strip(" .")
    raise ValueError(f"Could not identify the product name in {source_path}")


def parse_response(raw: str) -> list[dict[str, str]]:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"LLM response is not valid JSON: {error}") from error
    if not isinstance(payload, dict) or not isinstance(
        payload.get("contraindications"), list
    ):
        raise ValueError("LLM JSON must contain a contraindications list")

    results = []
    for item in payload["contraindications"]:
        if not isinstance(item, dict):
            raise ValueError("Each contraindication must be a JSON object")
        condition = item.get("condition")
        passage = item.get("passage")
        if not isinstance(condition, str) or not condition.strip():
            raise ValueError("Each contraindication needs a condition string")
        if not isinstance(passage, str) or not passage.strip():
            raise ValueError("Each contraindication needs a passage string")
        results.append({"condition": condition.strip(), "passage": passage.strip()})
    return results


def extract_conditions(drug: str, evidence: str, usage: dict[str, int]):
    raw = ask(
        USER_PROMPT.format(drug=drug, evidence=evidence),
        system=SYSTEM,
        run=0,
        temperature=0,
        usage=usage,
    )
    return parse_response(raw)


def triple_row(drug, candidate, result, provenance, ingredient_slugs):
    condition = result["condition"]
    condition_slug = canon(condition)
    passage = result["passage"]
    product_name = candidate.get("product_name") or product_name_from_rcp(
        ROOT / candidate["source"]
    )
    object_id = f"contraindication_{condition_slug}" if condition_slug else ""
    authority = (provenance.get(candidate["source"], {}).get("authority_level") or "").strip()
    collected_on = (provenance.get(candidate["source"], {}).get("collected_on") or "").strip()
    row = dict(zip(COLUMNS, [
        f"medicament_{slug(product_name)}",
        "medicament",
        "contraindicated_in",
        object_id,
        "contraindication",
        candidate["source"],
        authority,
        collected_on,
        passage,
    ]))

    reason = None
    if not condition_slug:
        reason = "empty_condition"
    elif re.search(r"\d", condition):
        reason = "numeric_condition"
    elif condition_slug in ingredient_slugs or condition_slug == slug(drug):
        reason = "condition_is_a_drug"
    elif authority not in {"1", "2", "3", "4"}:
        reason = "bad_authority_level"
    elif normalize_whitespace(passage) not in normalize_whitespace(
        candidate["evidence"]
    ):
        reason = "passage_not_in_candidate"
    elif not source_contains_evidence(ROOT / candidate["source"], passage):
        reason = "passage_not_in_source"
    return row, reason


def write_csv(path: Path, columns, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_vocab(vocab_raw, entities):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for entity_id, (entity_type, label) in sorted(entities.items()):
        writer.writerow(["entity", entity_id, entity_type, "", label])
    additions = buffer.getvalue()
    VOCAB_ADDITIONS.write_text(
        ",".join(VOCAB_COLUMNS) + "\n" + additions,
        encoding="utf-8",
    )
    MERGED_VOCAB.write_text(
        vocab_raw.replace("\r\n", "\n").rstrip("\n") + "\n" + additions,
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract ANPP RCP contraindications as product-to-condition triples."
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="maximum contraindication excerpts to process")
    parser.add_argument("--drug", default="",
                        help="process only matching medicine names")
    parser.add_argument("--pause", type=float, default=1.0,
                        help="seconds to wait after each uncached Groq request")
    args = parser.parse_args()
    if args.limit < 0 or args.pause < 0:
        parser.error("--limit and --pause must not be negative")

    provenance = load_provenance()
    candidates = select_rcp_candidates(clinical_candidates(), provenance)
    if args.drug:
        candidates = [
            candidate for candidate in candidates
            if args.drug.casefold() in candidate["subject_candidate"].casefold()
        ]
    if args.limit:
        candidates = candidates[:args.limit]
    for candidate in candidates:
        candidate["product_name"] = product_name_from_rcp(
            ROOT / candidate["source"]
        )

    known_ids, ingredient_slugs, vocab_raw = load_vocab()
    entities = {}
    kept = []
    rejected = []
    seen = set()
    usage = {"api_requests": 0, "cache_hits": 0, "successful_responses": 0}
    request_failed = False

    for candidate in candidates:
        drug = candidate["subject_candidate"]
        before_requests = usage["api_requests"]
        try:
            results = extract_conditions(drug, candidate["evidence"], usage)
        except RuntimeError as error:
            print(f"LLM request failed for {drug} ({candidate['source_locator']}): {error}")
            request_failed = True
            break
        except ValueError as error:
            rejected.append({
                **dict.fromkeys(COLUMNS, ""),
                "subject": f"medicament_{slug(candidate['product_name'])}",
                "subject_type": "medicament",
                "relation": "contraindicated_in",
                "source_file": candidate["source"],
                "passage": candidate["evidence"],
                "reason": f"invalid_llm_response: {error}",
                "source_locator": candidate["source_locator"],
            })
            continue

        for result in results:
            row, reason = triple_row(
                drug, candidate, result, provenance, ingredient_slugs
            )
            if reason:
                rejected.append({
                    **row,
                    "reason": reason,
                    "source_locator": candidate["source_locator"],
                })
                continue
            key = (row["subject"], row["object"], row["source_file"])
            if key in seen:
                continue
            seen.add(key)
            kept.append(row)
            for entity_id, entity_type, label in (
                (row["subject"], "medicament", candidate["product_name"]),
                (row["object"], "contraindication", result["condition"]),
            ):
                if entity_id not in known_ids and entity_id not in entities:
                    entities[entity_id] = (entity_type, label)

        if usage["api_requests"] > before_requests and args.pause:
            time.sleep(args.pause)

    GRAPH.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT, COLUMNS, kept)
    write_csv(REJECTED, REJECTED_COLUMNS, rejected)
    write_vocab(vocab_raw, entities)
    print(
        f"RCP excerpts: {len(candidates)} | triples: {len(kept)} | "
        f"rejected: {len(rejected)} | Groq requests: {usage['api_requests']} | "
        f"cache hits: {usage['cache_hits']} | successful responses: "
        f"{usage['successful_responses']}"
    )
    return 1 if request_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
