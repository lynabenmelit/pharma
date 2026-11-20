import sys, json, csv
from pathlib import Path
from datetime import date
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from src.llm import MODEL
from src.normalizer import normalize_text
from src.search.rag_pipeline import answer_question, retrieve_documents

# ---- CONFIGURATION ----
QUESTION_IDS = (
    "Q01", "Q02", "Q09", "Q10", "Q11", "Q14",
    "Q16", "Q23", "Q27", "Q28",
)
N_SUB = 3            # number of sub-questions
RUNS = 3             # how many times to ask
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
)
# -----------------------

QUESTIONS_FILE = BASE / "tests" / "test_questions.json"
with open(QUESTIONS_FILE, encoding="utf-8") as f:
    questions = json.load(f)["questions"]

rows = []
for q in (question for question in questions if question["id"] in QUESTION_IDS):
    expected_values = q.get("expected_values", [])
    is_refusal = q.get("expected_behavior") in REFUSAL_BEHAVIORS
    expected_sources = q.get("expected_sources", [])

    for mode in MODES:
        for run in range(RUNS):
            documents = retrieve_documents(
                q["question"],
                mode=mode,
                bm25_weight=BM25_WEIGHT,
            )
            retrieved_sources = ", ".join(document.title for document in documents)
            answer = answer_question(
                q["question"],
                documents=documents,
                run=run,
                temperature=TEMPERATURE,
                mode=mode,
                bm25_weight=BM25_WEIGHT,
            )
            normalized_answer = normalize_text(answer)

            if is_refusal:
                matched_values = []
                missing_values = list(expected_values)
                refused = any(
                    normalize_text(marker) in normalized_answer
                    for marker in REFUSAL_MARKERS
                )
                coverage = 100.0 if refused else 0.0
                if refused:
                    verdict = "correct"
                    error_type = "none"
                    comment = "LLM refused outside-scope or insufficient-information request."
                else:
                    verdict = "wrong"
                    error_type = "no_refusal"
                    comment = "LLM did not clearly refuse the out-of-scope request."
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
                    verdict = "correct"
                    error_type = "none"
                    comment = "LLM included all expected facts."
                elif matched_values:
                    verdict = "partial"
                    error_type = "missing_info"
                    comment = f"LLM missed: {', '.join(missing_values)}"
                else:
                    verdict = "wrong"
                    error_type = "missing_knowledge"
                    comment = f"LLM missed all expected facts: {', '.join(missing_values)}"

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
                else None
            )

            for sub in range(1, N_SUB + 1):
                rows.append({
                    "date": date.today().isoformat(),
                    "model": MODEL,
                    "temperature": TEMPERATURE,
                    "retrieval_mode": mode,
                    "bm25_weight": BM25_WEIGHT if mode == "hybrid" else "",
                    "question_id": q["id"],
                    "run": run + 1,
                    "sub_question": sub,
                    "prompt": q["question"] if sub == 1 else "(same prompt)",
                    "retrieved_sources": retrieved_sources if sub == 1 else "(see first line)",
                    "matched_sources": ", ".join(matched_sources),
                    "missing_sources": ", ".join(missing_sources),
                    "source_hit_rate_percent": source_hit_rate,
                    "llm_answer": answer if sub == 1 else "(see first line of this run)",
                    "expected_answer": q["expected_answer"] if sub == 1 else "(see first line)",
                    "matched_values": ", ".join(matched_values),
                    "missing_values": ", ".join(missing_values),
                    "fact_coverage_percent": coverage,
                    "verdict": verdict,
                    "error_type": error_type,
                    "comment": comment,
                })

out = BASE / "tests" / "results_week1.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter=";")
    w.writeheader()
    w.writerows(rows)
print("Saved:", out)

xlsx_out = BASE / "reports" / "week2_comparison.xlsx"
xlsx_out.parent.mkdir(parents=True, exist_ok=True)
workbook = Workbook()
sheet = workbook.active
sheet.title = "comparison"
headers = list(rows[0].keys())
sheet.append(headers)
for row in rows:
    sheet.append([row[header] for header in headers])
sheet.freeze_panes = "A2"
sheet.auto_filter.ref = sheet.dimensions
for cell in sheet[1]:
    cell.font = Font(bold=True)
    cell.fill = PatternFill("solid", fgColor="D9EAF7")
for row in sheet.iter_rows():
    for cell in row:
        cell.alignment = Alignment(vertical="top", wrap_text=True)

summary = workbook.create_sheet("summary")
summary.append([
    "retrieval_mode",
    "runs",
    "mean_fact_coverage_percent",
    "correct",
    "partial",
    "wrong",
])
for mode in MODES:
    mode_rows = [row for row in rows if row["retrieval_mode"] == mode]
    unique_runs = [row for row in mode_rows if row["sub_question"] == 1]
    summary.append([
        mode,
        len(unique_runs),
        round(
            sum(row["fact_coverage_percent"] for row in unique_runs)
            / len(unique_runs),
            1,
        ),
        sum(row["verdict"] == "correct" for row in unique_runs),
        sum(row["verdict"] == "partial" for row in unique_runs),
        sum(row["verdict"] == "wrong" for row in unique_runs),
    ])
for cell in summary[1]:
    cell.font = Font(bold=True)
    cell.fill = PatternFill("solid", fgColor="D9EAF7")
workbook.save(xlsx_out)
print("Saved:", xlsx_out)