import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VOCABULARY = ROOT / "data" / "graph" / "vocab.csv"
DEFAULT_TRIPLES = ROOT / "data" / "graph" / "triples_template.csv"
REQUIRED_COLUMNS = (
    "subject",
    "subject_type",
    "relation",
    "object",
    "object_type",
    "source_file",
    "authority_level",
    "collected_on",
    "passage",
)
ENTITY_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
COLLECTION_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_vocabulary(
    vocabulary_path: Path,
) -> tuple[set[str], dict[str, set[tuple[str, str]]], dict[str, str]]:
    entity_types: set[str] = set()
    predicates: dict[str, set[tuple[str, str]]] = {}
    entities: dict[str, str] = {}

    with vocabulary_path.open(encoding="utf-8-sig", newline="") as vocabulary_file:
        reader = csv.DictReader(vocabulary_file)
        expected_columns = {"kind", "name", "domain", "range", "description"}
        if reader.fieldnames is None or not expected_columns.issubset(reader.fieldnames):
            raise ValueError(
                "Vocabulary must contain: "
                + ", ".join(sorted(expected_columns))
            )

        rows = list(reader)

    for line_number, row in enumerate(rows, start=2):
        kind = (row.get("kind") or "").strip()
        name = (row.get("name") or "").strip()
        if not name:
            raise ValueError(f"Vocabulary row {line_number}: missing name")
        if kind == "entity_type":
            if name in entity_types:
                raise ValueError(f"Vocabulary row {line_number}: duplicate entity type {name}")
            entity_types.add(name)
        elif kind not in {"predicate", "entity"}:
            raise ValueError(f"Vocabulary row {line_number}: unknown kind {kind}")

    for line_number, row in enumerate(rows, start=2):
        kind = (row.get("kind") or "").strip()
        name = (row.get("name") or "").strip()
        if kind == "predicate":
            domain = (row.get("domain") or "").strip()
            object_range = (row.get("range") or "").strip()
            if not domain or not object_range:
                raise ValueError(
                    f"Vocabulary row {line_number}: {name} needs a domain and range"
                )
            if domain not in entity_types or object_range not in entity_types:
                raise ValueError(
                    f"Vocabulary row {line_number}: {name} uses an undeclared entity type"
                )
            allowed_types = predicates.setdefault(name, set())
            type_pair = (domain, object_range)
            if type_pair in allowed_types:
                raise ValueError(
                    f"Vocabulary row {line_number}: duplicate predicate "
                    f"{name} for {domain} -> {object_range}"
                )
            allowed_types.add(type_pair)
        elif kind == "entity":
            entity_type = (row.get("domain") or "").strip()
            if entity_type not in entity_types:
                raise ValueError(
                    f"Vocabulary row {line_number}: {name} uses an undeclared entity type"
                )
            if not ENTITY_ID.fullmatch(name):
                raise ValueError(
                    f"Vocabulary row {line_number}: entity ID {name} must be "
                    "lowercase ASCII with underscores"
                )
            if not (row.get("description") or "").strip():
                raise ValueError(
                    f"Vocabulary row {line_number}: entity {name} needs a readable label"
                )
            if name in entities:
                raise ValueError(f"Vocabulary row {line_number}: duplicate entity ID {name}")
            entities[name] = entity_type

    return entity_types, predicates, entities


def normalize_passage(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def passage_in_source(source_path: Path, passage: str) -> bool:
    source_text = source_path.read_text(encoding="utf-8-sig", errors="replace")
    return normalize_passage(passage) in normalize_passage(source_text)


def validate_triples(
    triples_path: Path, vocabulary_path: Path, source_root: Path = ROOT
) -> tuple[list[str], int]:
    entity_types, predicates, entities = load_vocabulary(vocabulary_path)
    errors: list[str] = []
    row_count = 0

    with triples_path.open(encoding="utf-8-sig", newline="") as triples_file:
        reader = csv.DictReader(triples_file)
        if reader.fieldnames is None:
            return ["Triples CSV is empty or has no header"], 0

        if tuple(reader.fieldnames) != REQUIRED_COLUMNS:
            return [
                "Triples CSV columns must be exactly: "
                + ", ".join(REQUIRED_COLUMNS)
            ], 0

        for line_number, row in enumerate(reader, start=2):
            row_count += 1
            if None in row:
                errors.append(f"Row {line_number}: too many CSV fields")
                continue

            missing_values = [
                column
                for column in REQUIRED_COLUMNS
                if column != "collected_on"
                if not (row.get(column) or "").strip()
            ]
            if missing_values:
                errors.append(
                    f"Row {line_number}: missing values for "
                    + ", ".join(missing_values)
                )
                continue

            collected_on = (row.get("collected_on") or "").strip()
            if collected_on and not COLLECTION_DATE.fullmatch(collected_on):
                errors.append(
                    f"Row {line_number}: collected_on must be YYYY-MM-DD or blank"
                )
            elif collected_on:
                try:
                    date.fromisoformat(collected_on)
                except ValueError:
                    errors.append(
                        f"Row {line_number}: collected_on is not a valid calendar date"
                    )

            authority_level = row["authority_level"].strip()
            if authority_level not in {"1", "2", "3", "4"}:
                errors.append(
                    f"Row {line_number}: unknown authority level {authority_level}"
                )

            source_file = Path(row["source_file"].strip())
            if source_file.is_absolute():
                errors.append(f"Row {line_number}: source_file must be repository-relative")
                continue
            source_path = (source_root / source_file).resolve()
            try:
                source_path.relative_to(source_root.resolve())
            except ValueError:
                errors.append(f"Row {line_number}: source_file escapes the repository root")
                continue
            if not source_path.is_file():
                errors.append(
                    f"Row {line_number}: source_file does not exist: {source_file}"
                )
                continue
            if not passage_in_source(source_path, row["passage"]):
                errors.append(
                    f"Row {line_number}: passage not found in {source_file}"
                )

            subject_type = row["subject_type"].strip()
            relation = row["relation"].strip()
            object_type = row["object_type"].strip()

            if subject_type not in entity_types:
                errors.append(f"Row {line_number}: unknown subject type {subject_type}")
                continue
            if object_type not in entity_types:
                errors.append(f"Row {line_number}: unknown object type {object_type}")
                continue
            if relation not in predicates:
                errors.append(f"Row {line_number}: unknown relation {relation}")
                continue

            allowed_types = predicates[relation]
            if (subject_type, object_type) not in allowed_types:
                if len(allowed_types) == 1:
                    expected_domain, expected_range = next(iter(allowed_types))
                    if subject_type != expected_domain:
                        errors.append(
                            f"Row {line_number}: {relation} expects subject type "
                            f"{expected_domain}, got {subject_type}"
                        )
                    if object_type != expected_range:
                        errors.append(
                            f"Row {line_number}: {relation} expects object type "
                            f"{expected_range}, got {object_type}"
                        )
                else:
                    allowed = ", ".join(
                        f"{domain} -> {object_range}"
                        for domain, object_range in sorted(allowed_types)
                    )
                    errors.append(
                        f"Row {line_number}: {relation} expects one of "
                        f"[{allowed}], got {subject_type} -> {object_type}"
                    )
            for value, entity_type, role in (
                (row["subject"].strip(), subject_type, "subject"),
                (row["object"].strip(), object_type, "object"),
            ):
                if entity_type == "literal":
                    continue
                if entities.get(value) != entity_type:
                    errors.append(
                        f"Row {line_number}: unknown {role} ID {value} "
                        f"for entity type {entity_type}"
                    )

    if row_count == 0:
        errors.append("Triples CSV contains no data rows")
    return errors, row_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check graph triples against the project's vocabulary."
    )
    parser.add_argument(
        "triples",
        nargs="?",
        type=Path,
        default=DEFAULT_TRIPLES,
        help="Triples CSV to validate (defaults to the working graph CSV).",
    )
    parser.add_argument(
        "--vocabulary",
        type=Path,
        default=DEFAULT_VOCABULARY,
        help="Vocabulary CSV (defaults to data/graph/vocab.csv).",
    )
    args = parser.parse_args()

    try:
        errors, row_count = validate_triples(args.triples, args.vocabulary)
    except (OSError, ValueError) as error:
        print(f"Cannot validate graph data: {error}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"OK: {row_count} triples are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
