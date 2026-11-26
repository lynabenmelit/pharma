import argparse
import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VOCABULARY = ROOT / "data" / "graph" / "vocab.csv"
DEFAULT_TRIPLES = ROOT / "data" / "graph" / "triples_template.csv"
REQUIRED_COLUMNS = (
    "subject",
    "subject_type",
    "predicate",
    "object",
    "object_type",
    "source",
    "source_locator",
    "evidence",
)


def load_vocabulary(
    vocabulary_path: Path,
) -> tuple[set[str], dict[str, tuple[str, str]]]:
    entity_types: set[str] = set()
    predicates: dict[str, tuple[str, str]] = {}

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
        elif kind not in {"predicate"}:
            raise ValueError(f"Vocabulary row {line_number}: unknown kind {kind}")

    for line_number, row in enumerate(rows, start=2):
        if (row.get("kind") or "").strip() != "predicate":
            continue
        name = (row.get("name") or "").strip()
        domain = (row.get("domain") or "").strip()
        object_range = (row.get("range") or "").strip()
        if not domain or not object_range:
            raise ValueError(f"Vocabulary row {line_number}: {name} needs a domain and range")
        if domain not in entity_types or object_range not in entity_types:
            raise ValueError(
                f"Vocabulary row {line_number}: {name} uses an undeclared entity type"
            )
        if name in predicates:
            raise ValueError(f"Vocabulary row {line_number}: duplicate predicate {name}")
        predicates[name] = (domain, object_range)

    return entity_types, predicates


def validate_triples(
    triples_path: Path, vocabulary_path: Path
) -> tuple[list[str], int]:
    entity_types, predicates = load_vocabulary(vocabulary_path)
    errors: list[str] = []
    row_count = 0

    with triples_path.open(encoding="utf-8-sig", newline="") as triples_file:
        reader = csv.DictReader(triples_file)
        if reader.fieldnames is None:
            return ["Triples CSV is empty or has no header"], 0

        missing_columns = set(REQUIRED_COLUMNS) - set(reader.fieldnames)
        if missing_columns:
            return [
                "Triples CSV is missing columns: "
                + ", ".join(sorted(missing_columns))
            ], 0

        for line_number, row in enumerate(reader, start=2):
            row_count += 1
            if None in row:
                errors.append(f"Row {line_number}: too many CSV fields")
                continue

            missing_values = [
                column
                for column in REQUIRED_COLUMNS
                if not (row.get(column) or "").strip()
            ]
            if missing_values:
                errors.append(
                    f"Row {line_number}: missing values for "
                    + ", ".join(missing_values)
                )
                continue

            subject_type = row["subject_type"].strip()
            predicate = row["predicate"].strip()
            object_type = row["object_type"].strip()

            if subject_type not in entity_types:
                errors.append(f"Row {line_number}: unknown subject type {subject_type}")
                continue
            if object_type not in entity_types:
                errors.append(f"Row {line_number}: unknown object type {object_type}")
                continue
            if predicate not in predicates:
                errors.append(f"Row {line_number}: unknown predicate {predicate}")
                continue

            expected_domain, expected_range = predicates[predicate]
            if subject_type != expected_domain:
                errors.append(
                    f"Row {line_number}: {predicate} expects subject type "
                    f"{expected_domain}, got {subject_type}"
                )
            if object_type != expected_range:
                errors.append(
                    f"Row {line_number}: {predicate} expects object type "
                    f"{expected_range}, got {object_type}"
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
