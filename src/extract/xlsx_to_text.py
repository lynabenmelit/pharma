"""Extract Excel workbooks into text files while preserving the raw folder layout."""
from pathlib import Path

from openpyxl import load_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW = PROJECT_ROOT / "data" / "raw"
OUT = PROJECT_ROOT / "data" / "text"


def workbook_to_text(workbook_path: Path) -> str:
    sections = []
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets:
            sections.append(f"[sheet: {sheet.title}]")
            for row in sheet.iter_rows(values_only=True):
                values = ["" if value is None else str(value) for value in row]
                if any(values):
                    sections.append("\t".join(values).strip())
    finally:
        workbook.close()
    return "\n".join(sections).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    count = 0
    for workbook_path in sorted(RAW.rglob("*.xlsx")):
        text = workbook_to_text(workbook_path)
        relative = workbook_path.relative_to(RAW).with_suffix(".txt")
        destination = OUT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        print(f"OK: {workbook_path.name} -> {relative.as_posix()} ({len(text)} characters)")
        count += 1
    print(f"Extracted {count} workbook(s).")


if __name__ == "__main__":
    main()
