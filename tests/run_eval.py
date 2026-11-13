import sys, json, csv
from pathlib import Path
from datetime import date
from openpyxl import Workbook

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from src.llm import MODEL
from src.search.rag_pipeline import answer_question

# ---- CONFIGURATION ----
QID = "Q10"          # the question you chose
N_SUB = 3            # number of sub-questions
RUNS = 3             # how many times to ask
TEMPERATURE = 0.3
# -----------------------

QUESTIONS_FILE = BASE / "tests" / "test_questions.json"
with open(QUESTIONS_FILE, encoding="utf-8") as f:
    questions = json.load(f)["questions"]

q = next((x for x in questions if x["id"] == QID), None)
if q is None:
    raise SystemExit(f"Question {QID} not found in {QUESTIONS_FILE}")

# Get the facts the LLM MUST mention to pass the test
expected_values = q.get("expected_values", [])

rows = []
for run in range(RUNS):
    # 1. ASK WITH LOCAL SOURCES: expected answers stay grader-only.
    answer = answer_question(q["question"], run=run, temperature=TEMPERATURE)
    
    # 2. AUTO-GRADE: Check if the LLM's answer contains the required facts (case-insensitive)
    matched_values = [
        val for val in expected_values if val.lower() in answer.lower()
    ]
    missing_values = [val for val in expected_values if val not in matched_values]
    coverage = (
        round(len(matched_values) / len(expected_values) * 100, 1)
        if expected_values
        else 0.0
    )
    
    # 3. DETERMINE VERDICT
    if not missing_values:
        verdict = "correct"
        error_type = "none"
        comment = "LLM included all expected facts."
    else:
        found_count = len(expected_values) - len(missing_values)
        if found_count > 0:
            verdict = "partial"
            error_type = "missing_info"
            comment = f"LLM missed: {', '.join(missing_values)}"
        else:
            verdict = "wrong"
            error_type = "missing_knowledge"
            comment = f"LLM missed all expected facts: {', '.join(missing_values)}"

    for sub in range(1, N_SUB + 1):
        rows.append({
            "date": date.today().isoformat(),
            "model": MODEL,
            "temperature": TEMPERATURE,
            "question_id": QID,
            "run": run + 1,
            "sub_question": sub,
            "prompt": q["question"] if sub == 1 else "(same prompt)",
            "llm_answer": answer if sub == 1 else "(see first line of this run)",
            "expected_answer": q["expected_answer"] if sub == 1 else "(see first line)",
            "matched_values": ", ".join(matched_values),
            "missing_values": ", ".join(missing_values),
            "fact_coverage_percent": coverage,
            "verdict": verdict,          # NOW AUTOMATICALLY FILLED!
            "error_type": error_type,    # NOW AUTOMATICALLY FILLED!
            "comment": comment,          # NOW AUTOMATICALLY FILLED!
        })

out = BASE / "tests" / "results_week1.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter=";")
    w.writeheader()
    w.writerows(rows)
print("Saved:", out)

xlsx_out = BASE / "tests" / "results_week1.xlsx"
workbook = Workbook()
sheet = workbook.active
sheet.title = "comparison"
headers = list(rows[0].keys())
sheet.append(headers)
for row in rows:
    sheet.append([row[header] for header in headers])
sheet.freeze_panes = "A2"
sheet.auto_filter.ref = sheet.dimensions
workbook.save(xlsx_out)
print("Saved:", xlsx_out)