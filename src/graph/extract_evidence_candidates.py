import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEXT_ROOT = ROOT / "data" / "text_clean"
PROVENANCE_PATH = ROOT / "data" / "provenance.csv"
NOMENCLATURE_PATH = ROOT / "data" / "medicaments_clean.csv"
DEFAULT_OUTPUT = ROOT / "data" / "graph" / "evidence_candidates.csv"
OUTPUT_COLUMNS = (
    "subject_candidate",
    "topic",
    "source",
    "source_locator",
    "evidence",
    "review_status",
    "source_check",
)
TARGET_HEADINGS = (
    ("indication", re.compile(r"^indications?(?: therapeutiques| and usage)?$")),
    ("contraindication", re.compile(r"^(?:contre[- ]?indications?|contraindications?)$")),
    ("adverse_effect", re.compile(r"^(?:effets indesirables|adverse reactions?)$")),
)
NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+){1,2}(?:\.?\s+|\s*[-–—]\s*)\S")
FORM_OR_STRENGTH = re.compile(r"\b(Formes?|Dosages?)\s*:\s*([^|]+)", re.IGNORECASE)
INTERACTION_CUES = re.compile(
    r"contre[- ]indication|association|pr[eé]caution|majoration|diminution|"
    r"interaction|risque|surveillance|[eé]viter|à prendre en compte",
    re.IGNORECASE,
)


def normalize_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", without_marks)


def normalize_heading(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(
        r"^\s*\d+(?:\.\d+)*\.?(?:\s*[-–—]\s*|\s+)",
        "",
        value,
    )
    return re.sub(r"[\s:]+$", "", value.strip())


def target_topic(line: str) -> str | None:
    normalized = normalize_heading(line)
    for topic, pattern in TARGET_HEADINGS:
        if pattern.fullmatch(normalized):
            return topic
    return None


def is_section_boundary(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if NUMBERED_HEADING.match(stripped):
        return True
    letters = [character for character in stripped if character.isalpha()]
    return (
        bool(letters)
        and len(stripped) <= 100
        and all(character.isupper() for character in letters)
    )


def split_paragraphs(text: str) -> list[str]:
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text):
        normalized = re.sub(r"\s+", " ", paragraph).strip()
        if len(normalized) >= 30 and not normalized.isdigit():
            paragraphs.append(normalized)
    return paragraphs


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def source_contains_evidence(source_path: Path, evidence: str) -> bool:
    source_text = source_path.read_text(encoding="utf-8-sig", errors="replace")
    return normalize_whitespace(evidence) in normalize_whitespace(source_text)


def extract_sections(text: str) -> list[tuple[str, str, list[str]]]:
    lines = text.splitlines()
    sections = []
    index = 0
    while index < len(lines):
        topic = target_topic(lines[index])
        if topic is None:
            index += 1
            continue

        heading = lines[index].strip()
        body_lines = []
        cursor = index + 1
        while cursor < len(lines) and not is_section_boundary(lines[cursor]):
            body_lines.append(lines[cursor])
            cursor += 1

        paragraphs = split_paragraphs("\n".join(body_lines))
        if paragraphs:
            sections.append((topic, heading, paragraphs))
        index = cursor
    return sections


def load_provenance() -> dict[tuple[str, str], str]:
    mapping: dict[tuple[str, str], str] = {}
    with PROVENANCE_PATH.open(encoding="utf-8-sig", newline="") as provenance_file:
        for row in csv.DictReader(provenance_file):
            source_path = Path(row.get("text_path", ""))
            family = normalize_key(source_path.parent.name)
            stem = normalize_key(source_path.stem)
            drug = (row.get("drug") or "").strip()
            if family and stem and drug:
                mapping[(family, stem)] = drug
    return mapping


def clinical_candidates() -> list[dict[str, str]]:
    provenance = load_provenance()
    candidates = []

    for text_path in sorted(TEXT_ROOT.rglob("*.txt")):
        relative = text_path.relative_to(TEXT_ROOT)
        if len(relative.parts) < 2:
            continue
        family = normalize_key(relative.parent.name)
        if family in {"ansm", "nomenclature"}:
            continue
        drug = provenance.get((family, normalize_key(text_path.stem)))
        if drug is None:
            continue

        text = text_path.read_text(encoding="utf-8", errors="replace")
        for topic, heading, paragraphs in extract_sections(text):
            for paragraph_number, paragraph in enumerate(paragraphs, start=1):
                candidates.append(
                    {
                        "subject_candidate": drug,
                        "topic": topic,
                        "source": f"data/text_clean/{relative.as_posix()}",
                        "source_locator": f"{heading} / paragraph {paragraph_number}",
                        "evidence": paragraph,
                        "review_status": "pending_review",
                    }
                )
    return candidates


def nomenclature_candidates() -> list[dict[str, str]]:
    candidates = []
    with NOMENCLATURE_PATH.open(encoding="utf-8-sig", newline="") as nomenclature_file:
        for row in csv.DictReader(nomenclature_file):
            drug = (row.get("dci_nom_de_la_substance") or "").strip()
            record_id = (row.get("n") or "").strip()
            remarks = row.get("remarques") or ""
            for match in FORM_OR_STRENGTH.finditer(remarks):
                label = match.group(1).casefold()
                excerpt = match.group(0).strip().rstrip("). ")
                topic = "form" if label.startswith("forme") else "strength"
                candidates.append(
                    {
                        "subject_candidate": drug,
                        "topic": topic,
                        "source": "data/medicaments_clean.csv",
                        "source_locator": f"n={record_id}, remarques",
                        "evidence": excerpt,
                        "review_status": "included_in_triples_at_ingredient_level",
                    }
                )
    return candidates


def interaction_candidates() -> list[dict[str, str]]:
    ansm_path = TEXT_ROOT / "ansm" / "ansm_thesaurus_interactions_2023-09.txt"
    with NOMENCLATURE_PATH.open(encoding="utf-8-sig", newline="") as nomenclature_file:
        ingredients = {
            normalize_key(row["dci_nom_de_la_substance"]): row["dci_nom_de_la_substance"].strip()
            for row in csv.DictReader(nomenclature_file)
            if row.get("dci_nom_de_la_substance")
        }

    lines = ansm_path.read_text(encoding="utf-8", errors="replace").splitlines()
    candidates = []
    index = 0
    while index < len(lines):
        heading = lines[index].strip()
        ingredient = ingredients.get(normalize_key(heading))
        if ingredient is None or heading != heading.upper() or not heading[0].isalpha():
            index += 1
            continue

        body_lines = []
        cursor = index + 1
        while cursor < len(lines) and not is_uppercase_heading(lines[cursor]):
            body_lines.append(lines[cursor])
            cursor += 1

        for paragraph_number, paragraph in enumerate(
            split_paragraphs("\n".join(body_lines)), start=1
        ):
            if INTERACTION_CUES.search(paragraph):
                candidates.append(
                    {
                        "subject_candidate": ingredient,
                        "topic": "interaction",
                        "source": "data/text_clean/ansm/ansm_thesaurus_interactions_2023-09.txt",
                        "source_locator": f"{heading} / paragraph {paragraph_number}",
                        "evidence": paragraph,
                        "review_status": "pending_review",
                    }
                )
        index = cursor
    return candidates


def is_uppercase_heading(line: str) -> bool:
    stripped = line.strip()
    letters = [character for character in stripped if character.isalpha()]
    return (
        bool(letters)
        and len(stripped) <= 100
        and all(character.isupper() for character in letters)
    )


def build_candidates(output_path: Path) -> tuple[dict[str, int], int, int]:
    candidates = (
        clinical_candidates()
        + nomenclature_candidates()
        + interaction_candidates()
    )
    source_matches = 0
    normalized_sources: dict[Path, str] = {}
    for candidate in candidates:
        source_path = ROOT / Path(candidate["source"])
        if source_path.is_file():
            if source_path not in normalized_sources:
                source_text = source_path.read_text(
                    encoding="utf-8-sig", errors="replace"
                )
                normalized_sources[source_path] = normalize_whitespace(source_text)
            source_match = (
                normalize_whitespace(candidate["evidence"])
                in normalized_sources[source_path]
            )
        else:
            source_match = False

        if source_match:
            candidate["source_check"] = "quote_found"
            source_matches += 1
        else:
            candidate["source_check"] = "quote_not_found"

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(candidates)

    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate["topic"]] = counts.get(candidate["topic"], 0) + 1
    return counts, source_matches, len(candidates) - source_matches


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract source excerpts as unverified graph candidates."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output CSV path (defaults to data/graph/evidence_candidates.csv).",
    )
    args = parser.parse_args()

    try:
        counts, source_matches, source_misses = build_candidates(args.output)
    except OSError as error:
        print(f"Cannot extract evidence candidates: {error}", file=sys.stderr)
        return 2

    total = sum(counts.values())
    print(f"Wrote {total} evidence candidates to {args.output}")
    print(f"Source quote found: {source_matches}; not found: {source_misses}")
    for topic, count in sorted(counts.items()):
        print(f"{topic}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
