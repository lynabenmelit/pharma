# DawaCheck

DawaCheck is a local-first medicine-information assistant. It builds a
searchable corpus from pharmaceutical documents, cleans and annotates the
corpus, retrieves relevant passages with BM25, and asks a language model to
answer only from those passages.

The project is intended for document retrieval, experimentation, and
evaluation. It is **not** a diagnostic tool and must not replace a doctor,
pharmacist, official product information, or emergency services.

## What the project does

The complete workflow is:

1. Collect trusted PDFs, HTML files, text files, and optional Excel data.
2. Record source URLs, dates, local paths, hashes, language, and authority in
   `data/provenance.csv`.
3. Extract supported source files into plain text.
4. Clean text and reject empty, corrupt, or duplicate documents.
5. Normalize medicine names, doses, forms, and ATC identifiers.
6. Split cleaned documents into bounded overlapping chunks.
7. Retrieve relevant chunks with an in-memory BM25 index.
8. Send only the selected local context to Groq.
9. Display the answer and the official URLs associated with the sources.
10. Evaluate answers against a fixed set of expected facts.

The language model is used after local retrieval; it is not used as the
primary search index and does not receive the expected evaluation answers.

## Repository layout

```text
pharma/
├── README.md
├── requirements.txt
├── config.py
├── .env                         # local secrets; ignored by Git
├── app/
│   └── app.py                  # Streamlit user interface
├── cache/
│   └── llm_cache.json          # cached model responses
├── data/
│   ├── raw/                    # original source files; never edited
│   │   ├── anpp/
│   │   ├── ansm/
│   │   ├── base-donnees_publique.medicaments/
│   │   ├── dailyMed/
│   │   ├── dzairPharma/
│   │   └── nomenclature/
│   ├── text/                   # extracted text, mirroring data/raw/
│   ├── text_clean/             # cleaned text used for chunking
│   ├── processed/              # space for processed source artifacts
│   ├── vector_db/              # reserved for future vector indexes
│   ├── provenance.csv          # source registry and provenance metadata
│   ├── clean_docs.csv          # accepted-document quality metadata
│   ├── rejected.csv            # rejected documents and reasons
│   ├── medicaments_40.xlsx     # input nomenclature workbook
│   ├── medicaments_clean.csv   # normalized nomenclature output
│   ├── chunks.jsonl            # retrieval corpus: one JSON object per line
│   └── chunks_report.json      # chunking statistics
├── src/
│   ├── llm.py                  # Groq API call, retries, and response cache
│   ├── collect/
│   │   ├── scraper.py          # download helper with no import side effects
│   │   └── add_hashes.py       # add SHA-256 hashes to provenance.csv
│   ├── extract/
│   │   ├── extractor.py        # PDF, HTML, and text extraction
│   │   ├── extract_text.py     # text-cleaning helper
│   │   ├── prepare.py          # cleaning, filtering, metadata, quality flags
│   │   └── xlsx_to_text.py     # optional workbook-to-text conversion
│   ├── normalize/
│   │   ├── units.py            # names and dose parsing
│   │   ├── nomenclature.py     # workbook normalization
│   │   └── normalizer.py       # exact and fuzzy medicine resolution
│   ├── search/
│   │   ├── chunk_documents.py  # chunk generation and metadata
│   │   ├── bm25.py             # tokenization and BM25 retrieval
│   │   └── rag_pipeline.py     # retrieval, context formatting, and answers
│   ├── reconcile/              # reserved for source conflict handling
│   └── verify/                 # reserved for answer verification
├── tests/
│   ├── test_questions.json     # 30-question evaluation set
│   ├── test_bm25.py
│   ├── test_chunk_documents.py
│   ├── test_normalizer.py
│   ├── run_eval.py             # model evaluation script
│   ├── results_week1.csv       # generated evaluation results
│   └── results_week1.xlsx      # generated spreadsheet results
└── notebooks/                  # exploratory notebook workspace
```

## Requirements

- Python 3.10 or newer is recommended.
- A Groq API key is required only when an uncached answer must be generated.
- The project uses local files for extraction, cleaning, chunking, and BM25
  retrieval.

Install the dependencies listed in `requirements.txt`:

| Package | Purpose |
|---|---|
| `requests` | HTTP requests to the Groq API |
| `python-dotenv` | Loading `.env` variables |
| `pandas` | Tabular data processing |
| `openpyxl` | Excel input and evaluation output |
| `beautifulsoup4` | HTML parsing support |
| `pymupdf` | PDF text extraction |
| `rank_bm25` | BM25 keyword retrieval |
| `rapidfuzz` | Typo-tolerant medicine matching |
| `streamlit` | Web application |

## Installation

From the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell execution policy prevents activation, use the virtual
environment interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create a `.env` file in the repository root:

```text
GROQ_API_KEY=your_groq_api_key
```

`.env`, virtual environments, Python caches, and `.pyc` files are ignored by
Git. Never commit an API key.

## Configuration

There are two configuration modules:

- `config.py` contains the model name and basic top-level paths.
- `src/prep_config.py` contains data-preparation paths and quality thresholds.

Current model and API behavior:

- API endpoint: Groq OpenAI-compatible chat-completions endpoint.
- Model: `openai/gpt-oss-120b`.
- Temperature used by the app: `0.3`.
- Request timeout: 60 seconds.
- HTTP 429 responses are retried up to three attempts with a 10-second delay.
- Successful responses are cached in `cache/llm_cache.json`.
- Cache keys include the model, system prompt, user prompt, run number, and
  temperature.

The data-preparation defaults are:

- minimum accepted text length: 300 characters;
- maximum garbage-character ratio: 0.25;
- dose outlier absolute cap: 10,000 mg;
- authority level: ANPP `1`, nomenclature `2`, DailyMed/ANSM/EMA `3`, and
  unknown sources `5` (lower is more authoritative).

## Preparing the corpus

Run commands from the repository root. The normal pipeline is:

```powershell
.\.venv\Scripts\python.exe src\extract\extractor.py
.\.venv\Scripts\python.exe src\extract\prepare.py
.\.venv\Scripts\python.exe src\normalize\nomenclature.py
.\.venv\Scripts\python.exe src\search\chunk_documents.py
```

### 1. Add source files

Place source files below the appropriate folder in `data/raw/`. The extractor
supports:

- `.pdf` through PyMuPDF;
- `.txt`;
- `.html` and `.htm`.

The directory layout below `data/raw/` is reproduced below `data/text/`.
Unsupported files are skipped by the extractor. Raw files are never modified.

For each source, add or update a row in `data/provenance.csv`. The registry
currently contains fields such as:

```text
doc_id, drug, source, url, collected_on, language,
authority_level, raw_path, text_path, sha256, terms_checked, remarks
```

The URL is later used to display the official source link in the app.

The optional downloader can be used from Python:

```python
from pathlib import Path
from src.collect.scraper import download_document

download_document(
    "https://example.org/document.pdf",
    Path("data/raw/example/document.pdf"),
)
```

The downloader uses a `DawaCheck/0.1` user agent, a 30-second timeout, and has
no network side effect when the module is imported. Check each site's terms,
robots policy, and redistribution rules before collecting documents.

### 2. Extract text

```powershell
.\.venv\Scripts\python.exe src\extract\extractor.py
```

Optional source and destination directories are supported:

```powershell
.\.venv\Scripts\python.exe src\extract\extractor.py `
  --source data\raw `
  --destination data\text
```

For Excel workbooks that should also become searchable text:

```powershell
.\.venv\Scripts\python.exe src\extract\xlsx_to_text.py
```

The workbook converter preserves sheet names and writes tab-separated rows
under the same relative folder structure in `data/text/`.

### 3. Clean and quality-check text

```powershell
.\.venv\Scripts\python.exe src\extract\prepare.py
```

The preparation step:

- normalizes Unicode and common ligatures;
- removes control characters, URLs, repeated short headers, and footers;
- rejoins words split across line endings;
- detects French, English, and Arabic text heuristically;
- fills missing metadata from `provenance.csv` or the file itself;
- normalizes medicine names without accents;
- extracts detected doses and converts comparable doses to mg;
- rejects text shorter than 300 characters;
- rejects text whose garbage-character ratio exceeds 0.25;
- rejects normalized duplicates;
- flags dose and document-length outliers without deleting them.

Outputs:

| File | Description |
|---|---|
| `data/text_clean/` | Accepted cleaned text, preserving source folders |
| `data/clean_docs.csv` | Accepted documents, metadata, dose data, and flags |
| `data/rejected.csv` | Rejected files and `too_short`, `ocr_garbage`, or duplicate reasons |
| `reports/week1_prep_report.json` | Counts by source and rejection/quality summary |

Quality flags are for review. A large dose can be legitimate when a notice
contains multiple strengths or concentration units.

### 4. Normalize nomenclature

```powershell
.\.venv\Scripts\python.exe src\normalize\nomenclature.py
```

The workbook cleaner:

- accepts slightly different column headings by matching keywords;
- removes empty rows and trims text cells;
- removes rows with neither a brand nor a DCI;
- creates accent-free normalized name columns;
- converts doses to mg when possible;
- marks dose outliers and unparsed doses;
- normalizes pharmaceutical forms and ATC codes;
- creates a canonical key in the form `dci|dose_mg|form`;
- removes duplicate rows.

The output is `data/medicaments_clean.csv`.

`MedicineResolver` can then resolve a query by exact DCI, brand, or ATC code,
and falls back to RapidFuzz matching. It returns an explicit `matched`,
`ambiguous`, or `unknown` result rather than silently selecting a medicine.

### 5. Build retrieval chunks

```powershell
.\.venv\Scripts\python.exe src\search\chunk_documents.py
```

Chunking reads `data/text_clean/` and writes:

- `data/chunks.jsonl`: one JSON object per chunk;
- `data/chunks_report.json`: document count, chunk count, and size statistics.

Chunks are paragraph-aware, no larger than 1,500 characters, and use up to
200 characters of word-boundary overlap. Each chunk includes:

```text
chunk_id, document, document_path, source, drug, drug_norm,
url, language, authority, chunk_index, n_chunks, n_chars, text
```

The current checked-in report describes 98 input documents, 3,330 chunks, an
average chunk size of 1,211.4 characters, and a largest chunk of 1,500
characters. Regenerate the report after changing the corpus; these numbers
will change.

## Running the application

Start the Streamlit interface:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app\app.py
```

Open the local URL shown by Streamlit, enter a medicine question, and select
**Search**.

For each non-empty question, the app:

1. loads the local chunk corpus;
2. tokenizes the question with lowercase and accent removal;
3. retrieves BM25 matches using text and medicine metadata;
4. selects up to four distinct source documents;
5. limits the combined model context to 12,000 characters;
6. asks Groq to answer only from the supplied local excerpts;
7. tells the model to disclose missing information instead of inventing it;
8. displays the answer and deduplicated official URLs.

The BM25 index is built in memory and cached for the process lifetime. It is
rebuilt automatically if a different chunks-file path is passed, but the app
process should be restarted after replacing `data/chunks.jsonl`.

If no chunks match, the application reports that no source documents were
retrieved. If `GROQ_API_KEY` is absent and the answer is not already cached,
the request fails with an explicit missing-key error.

## Evaluation

The evaluation set is `tests/test_questions.json`. It currently contains 30
validated questions with categories, medicines, expected answers, expected
facts, reference authority, and reference passages.

Choose a question by editing `QID` in `tests/run_eval.py`:

```python
QID = "Q10"
```

Then run:

```powershell
.\.venv\Scripts\python.exe tests\run_eval.py
```

The script asks the selected question three times, with temperature `0.3`,
and writes:

- `tests/results_week1.csv`, semicolon-delimited and UTF-8 with BOM;
- `tests/results_week1.xlsx`, with frozen headers and filters.

Each result records the model, question, run, expected answer, matched facts,
missing facts, factual coverage percentage, verdict, error type, and comment.
Verdicts are:

- `correct`: every expected value was found;
- `partial`: at least one, but not every, expected value was found;
- `wrong`: none of the expected values was found.

The expected answer and expected facts are grader-only data. They are not
passed into the retrieval prompt.

## Tests

Run the focused unit-test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Run an individual test module:

```powershell
.\.venv\Scripts\python.exe -m unittest tests\test_normalizer.py
```

The tests cover:

- accent-removing tokenization and BM25 ranking;
- medicine metadata improving retrieval;
- JSONL chunk loading and result shape;
- empty and invalid chunking inputs;
- exact, brand, ATC, typo, unknown, and ambiguous medicine resolution;
- canonical medicine keys containing dose and form.

## Useful maintenance commands

Add SHA-256 hashes for files registered in the provenance CSV:

```powershell
.\.venv\Scripts\python.exe src\collect\add_hashes.py
```

Inspect the cached LLM responses:

```powershell
Get-Content cache\llm_cache.json
```

Clear the local model cache when a fresh response is required:

```powershell
Remove-Item cache\llm_cache.json
```

Only remove that specific cache file; the raw and processed corpus are
separate project data and should not be deleted casually.

## Data and provenance practices

- Keep original downloads in `data/raw/` and do not edit them in place.
- Keep extracted text in `data/text/` and cleaned text in `data/text_clean/`.
- Register every source URL and local path in `data/provenance.csv`.
- Preserve collection dates, authority levels, language, and hashes.
- Review rejection and outlier reports before relying on a corpus update.
- Do not treat a source's authority score as a clinical conclusion; it is a
  retrieval and review aid.
- Follow the terms of each source website and avoid collecting restricted
  content.
- Do not commit credentials, private documents, or unlicensed data.

## Limitations and safety

DawaCheck can return incomplete, stale, incorrectly extracted, or
misinterpreted information. BM25 is keyword-based and does not guarantee that
the best clinical passage is retrieved. The model can also misunderstand
retrieved text, even when it is instructed not to invent information.

Always verify important information against the current official product
information and consult a qualified healthcare professional, especially for:

- diagnosis or treatment decisions;
- dosage changes;
- contraindications, interactions, pregnancy, or pediatric use;
- allergies or adverse reactions;
- overdose, poisoning, or emergency symptoms.

## License and project status

No license file is currently included in this repository. Confirm the
licensing terms for this project and every imported source before distributing
it. The `reconcile/`, `verify/`, and `vector_db/` areas are reserved for
future work; the current implemented retrieval path is local BM25 plus
Groq-backed answer generation.
