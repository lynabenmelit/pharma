"""Run resumable, per-answer evaluation across the 30-question test set."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.llm import MODEL  # noqa: E402
from src.normalizer import normalize_text  # noqa: E402
from src.search.rag_pipeline import (  # noqa: E402
    _must_refuse_personal_request,
    SourceDocument,
    answer_question,
    retrieve_documents,
)
from src.verify.citations import verify_citations  # noqa: E402

RUNS = 3
TEMPERATURE = 0.3
MODES = ("bm25", "semantic", "hybrid")
BM25_WEIGHT = 0.5
REFUSAL_BEHAVIORS = {"refuse", "refusal"}
REFUSAL_MARKERS = (
    "ne peux pas",
    "je ne peux",
    "pas repondre",
    "hors perimetre",
    "consulter un medecin",
    "consulter un pharmacien",
    "لا أستطيع",
)
FIELDS = (
    "date",
    "model",
    "temperature",
    "retrieval_mode",
    "bm25_weight",
    "question_id",
    "run",
    "prompt",
    "retrieved_sources",
    "matched_sources",
    "missing_sources",
    "source_hit_rate_percent",
    "llm_answer",
    "cited_files",
    "valid_citations",
    "invalid_citations",
    "citation_count",
    "valid_citation_count",
    "invalid_citation_count",
    "citation_valid_rate_percent",
    "expected_answer",
    "matched_values",
    "missing_values",
    "fact_coverage_percent",
    "verdict",
    "error_type",
    "comment",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question-ids",
        nargs="+",
        help="question IDs to run (default: all questions)",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=MODES,
        default=MODES,
        help="retrieval modes to run (default: all modes)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=RUNS,
        help="number of runs per question and mode (default: %(default)s)",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=20,
        help="minimum delay after each generated answer (default: 20)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/results_rerun_30.csv"),
        help="semicolon-delimited checkpoint CSV path",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/rerun_30_comparison.xlsx"),
        help="summary workbook path",
    )
    args = parser.parse_args()
    if args.pause_seconds < 0:
        parser.error("--pause-seconds must not be negative")
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    return args


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else BASE / path


def _key(row: dict[str, str]) -> tuple[str, str, int]:
    return row["question_id"], row["retrieval_mode"], int(row["run"])


def _grade_answer(
    question: dict,
    mode: str,
    run: int,
    documents: list,
    answer: str,
) -> dict:
    expected_values = question.get("expected_values", [])
    expected_sources = question.get("expected_sources", [])
    is_refusal = question.get("expected_behavior") in REFUSAL_BEHAVIORS
    normalized_answer = normalize_text(answer)

    if is_refusal:
        refused = any(
            normalize_text(marker) in normalized_answer
            for marker in REFUSAL_MARKERS
        )
        matched_values = []
        missing_values = []
        coverage = 100.0 if refused else 0.0
        verdict = "correct" if refused else "wrong"
        error_type = "none" if refused else "no_refusal"
        comment = (
            "The answer refused the out-of-scope or personalized request."
            if refused
            else "The answer did not clearly refuse the request."
        )
    else:
        matched_values = [
            value
            for value in expected_values
            if normalize_text(value) in normalized_answer
        ]
        missing_values = [
            value
            for value in expected_values
            if normalize_text(value) not in normalized_answer
        ]
        coverage = (
            round(len(matched_values) / len(expected_values) * 100, 1)
            if expected_values
            else 0.0
        )
        if not missing_values:
            verdict, error_type = "correct", "none"
            comment = "The answer included all expected facts."
        elif matched_values:
            verdict, error_type = "partial", "missing_info"
            comment = f"Missing: {', '.join(missing_values)}"
        else:
            verdict, error_type = "wrong", "missing_knowledge"
            comment = f"Missing all expected facts: {', '.join(missing_values)}"

    matched_sources = [
        source
        for source in expected_sources
        if any(
            normalize_text(source) in normalize_text(document.title)
            for document in documents
        )
    ]
    missing_sources = [
        source for source in expected_sources if source not in matched_sources
    ]
    source_hit_rate = (
        round(len(matched_sources) / len(expected_sources) * 100, 1)
        if expected_sources
        else ""
    )
    citation_result = verify_citations(answer, documents)
    citation_rate = (
        round(
            len(citation_result["verified"]) / len(citation_result["cited"]) * 100,
            1,
        )
        if citation_result["cited"]
        else ""
    )

    return {
        "date": date.today().isoformat(),
        "model": MODEL,
        "temperature": TEMPERATURE,
        "retrieval_mode": mode,
        "bm25_weight": BM25_WEIGHT if mode == "hybrid" else "",
        "question_id": question["id"],
        "run": run + 1,
        "prompt": question["question"],
        "retrieved_sources": ", ".join(document.title for document in documents),
        "matched_sources": ", ".join(matched_sources),
        "missing_sources": ", ".join(missing_sources),
        "source_hit_rate_percent": source_hit_rate,
        "llm_answer": answer,
        "cited_files": ", ".join(citation_result["cited"]),
        "valid_citations": ", ".join(citation_result["verified"]),
        "invalid_citations": ", ".join(citation_result["unsupported"]),
        "citation_count": len(citation_result["cited"]),
        "valid_citation_count": len(citation_result["verified"]),
        "invalid_citation_count": len(citation_result["unsupported"]),
        "citation_valid_rate_percent": citation_rate,
        "expected_answer": question["expected_answer"],
        "matched_values": ", ".join(matched_values),
        "missing_values": ", ".join(missing_values),
        "fact_coverage_percent": coverage,
        "verdict": verdict,
        "error_type": error_type,
        "comment": comment,
    }


def _read_results(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def _refresh_citation_fields(row: dict[str, str]) -> None:
    titles = [
        title.strip()
        for title in row.get("retrieved_sources", "").split(", ")
        if title.strip()
    ]
    documents = [
        SourceDocument(title=title, content="", source=title)
        for title in titles
    ]
    citation_result = verify_citations(row.get("llm_answer", ""), documents)
    row.update({
        "cited_files": ", ".join(citation_result["cited"]),
        "valid_citations": ", ".join(citation_result["verified"]),
        "invalid_citations": ", ".join(citation_result["unsupported"]),
        "citation_count": str(len(citation_result["cited"])),
        "valid_citation_count": str(len(citation_result["verified"])),
        "invalid_citation_count": str(len(citation_result["unsupported"])),
        "citation_valid_rate_percent": (
            str(round(
                len(citation_result["verified"])
                / len(citation_result["cited"]) * 100,
                1,
            ))
            if citation_result["cited"] else ""
        ),
    })


def _rewrite_checkpoint(path: Path, rows: list[dict[str, str]]) -> None:
    temporary_path = path.with_name(path.name + ".tmp")
    with temporary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, path)


def _write_report(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    comparison = workbook.active
    comparison.title = "comparison"
    comparison.append(list(FIELDS))
    for row in rows:
        comparison.append([row.get(field, "") for field in FIELDS])
    comparison.freeze_panes = "A2"
    comparison.auto_filter.ref = comparison.dimensions

    summary = workbook.create_sheet("summary")
    summary.append([
        "retrieval_mode",
        "answers",
        "answers_without_citations",
        "mean_fact_coverage_percent",
        "correct",
        "partial",
        "wrong",
        "valid_citations",
        "total_citations",
        "citation_valid_rate_percent",
    ])
    for mode in MODES:
        mode_rows = [row for row in rows if row["retrieval_mode"] == mode]
        citation_rows = [
            row for row in mode_rows if int(row.get("citation_count", 0) or 0)
        ]
        total_citations = sum(int(row["citation_count"]) for row in citation_rows)
        valid_citations = sum(
            int(row["valid_citation_count"]) for row in citation_rows
        )
        summary.append([
            mode,
            len(mode_rows),
            sum(
                int(row.get("citation_count", 0) or 0) == 0
                for row in mode_rows
            ),
            round(
                sum(float(row["fact_coverage_percent"]) for row in mode_rows)
                / len(mode_rows),
                1,
            ) if mode_rows else "",
            sum(row["verdict"] == "correct" for row in mode_rows),
            sum(row["verdict"] == "partial" for row in mode_rows),
            sum(row["verdict"] == "wrong" for row in mode_rows),
            valid_citations,
            total_citations,
            round(valid_citations / total_citations * 100, 1)
            if total_citations else "",
        ])

    audit = workbook.create_sheet("citation_audit")
    audit.append([
        "question_id",
        "answer_rows",
        "answers_with_citations",
        "answers_without_citations",
        "valid_citations",
        "total_citations",
        "citation_valid_rate_percent",
    ])
    by_question: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_question[row["question_id"]].append(row)
    for question_id in sorted(by_question):
        question_rows = by_question[question_id]
        cited_rows = [
            row for row in question_rows
            if int(row.get("citation_count", 0) or 0)
        ]
        total = sum(int(row["citation_count"]) for row in cited_rows)
        valid = sum(int(row["valid_citation_count"]) for row in cited_rows)
        audit.append([
            question_id,
            len(question_rows),
            len(cited_rows),
            len(question_rows) - len(cited_rows),
            valid,
            total,
            round(valid / total * 100, 1) if total else "",
        ])

    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="D9EAF7")
        for row in sheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
    workbook.save(path)


def main() -> None:
    args = parse_args()
    output = _resolve_path(args.output)
    report = _resolve_path(args.report)
    question_data = json.loads(
        (BASE / "tests" / "test_questions.json").read_text(encoding="utf-8")
    )["questions"]
    question_by_id = {question["id"]: question for question in question_data}
    selected_ids = args.question_ids or list(question_by_id)
    unknown_ids = sorted(set(selected_ids) - set(question_by_id))
    if unknown_ids:
        raise ValueError(f"Unknown question IDs: {', '.join(unknown_ids)}")
    selected_questions = [
        question_by_id[question_id] for question_id in selected_ids
    ]

    existing_rows = _read_results(output)
    if existing_rows and set(existing_rows[0]) != set(FIELDS):
        raise ValueError(
            f"Existing checkpoint has a different CSV schema: {output}"
        )
    if existing_rows:
        for row in existing_rows:
            _refresh_citation_fields(row)
        _rewrite_checkpoint(output, existing_rows)
    completed = {_key(row) for row in existing_rows}
    scheduled = {
        (question["id"], mode, run + 1)
        for question in selected_questions
        for mode in MODES
        for run in range(RUNS)
    }
    remaining = scheduled - completed
    if not remaining:
        print(f"All {len(scheduled)} requested answers are already saved in {output}")
        _write_report(existing_rows, report)
        print(f"Saved: {report}")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output.exists() or output.stat().st_size == 0
    pending_count = len(remaining)
    with output.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter=";")
        if write_header:
            writer.writeheader()
            handle.flush()
            os.fsync(handle.fileno())

        finished = 0
        for question in selected_questions:
            for mode in args.modes:
                for run in range(args.runs):
                    key = (question["id"], mode, run + 1)
                    if key not in remaining:
                        continue
                    documents = retrieve_documents(
                        question["question"],
                        mode=mode,
                        bm25_weight=BM25_WEIGHT,
                    )
                    answer = answer_question(
                        question["question"],
                        documents=documents,
                        run=run,
                        temperature=TEMPERATURE,
                        mode=mode,
                        bm25_weight=BM25_WEIGHT,
                    )
                    row = _grade_answer(question, mode, run, documents, answer)
                    writer.writerow(row)
                    handle.flush()
                    os.fsync(handle.fileno())
                    existing_rows.append(row)
                    remaining.remove(key)
                    finished += 1
                    print(
                        f"[{finished}/{pending_count}] {question['id']} "
                        f"{mode} run {run + 1}: {row['verdict']}; "
                        f"citations {row['valid_citations'] or 'none'}"
                    )
                    if (
                        args.pause_seconds
                        and finished < pending_count
                        and not _must_refuse_personal_request(question["question"])
                    ):
                        time.sleep(args.pause_seconds)

    _write_report(existing_rows, report)
    print(f"Saved {len(existing_rows)} answer rows: {output}")
    print(f"Saved: {report}")


if __name__ == "__main__":
    main()
