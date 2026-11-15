# DawaCheck

DawaCheck is a local-first medicine-information assistant. It is designed to
download trusted medicine documents, extract structured information, normalize
medicine names, and answer questions with retrieval-augmented generation.

## Project structure

```text
pharma/
├── README.md
├── .gitignore            # excludes .env, virtual environments, and Python caches
├── requirements.txt
├── config.py
├── data/
│   ├── raw/              # original PDFs / HTML, never edited
│   │   ├── dailymed/     # DailyMed PDFs
│   │   ├── anpp/         # ANPP PDFs
│   │   └── nomenclature/ # extracted Excel subsets
│   ├── text/             # text extracted from PDFs and HTML
│   ├── medicaments_40.xlsx
│   └── provenance.csv    # source, url, date, language, authority level
├── cache/
│   └── llm_cache.json    # saved LLM answers (replay the test set)
├── src/
│   ├── llm.py            # Groq call, cache, and retry
│   ├── collect/          # source collection helpers
│   ├── extract/          # PDF/HTML extraction and data preparation
│   ├── normalize/        # nomenclature and medicine-name matching
│   ├── search/           # local retrieval and RAG pipeline
│   ├── reconcile/        # reserved for source conflict handling
│   └── verify/           # reserved for answer verification
├── app/
│   └── app.py            # Streamlit interface
├── tests/
│   ├── test_questions.json # questions and expected facts
│   ├── test_normalizer.py  # normalizer tests
│   └── run_eval.py         # evaluation against the question set
├── notebooks/            # Colab notebooks (embeddings)
└── reports/
    ├── week1_prep_report.json
    └── sources_terms.md   # terms of use and robots.txt of each site
```

## Setup

1. Create a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the project dependencies:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Add your Groq API key to a new `.env` file:

   ```text
   GROQ_API_KEY=your_key_here
   ```

4. Put source PDFs and HTML files in `data/raw/`. Generated text files belong
   in `data/text/`; cleaned text is written to `data/text_clean/`.

### Add and extract sources

For a new PDF:

1. Copy it into the appropriate subfolder under `data/raw/`.
2. Add its source URL and local paths as a row in `data/provenance.csv`.
3. Run the extractor from the project root:

```powershell
.\.venv\Scripts\python.exe src\extract\extractor.py
```

The command recursively extracts PDFs, text, and HTML files from `data/raw/`
into matching `.txt` files under `data/text/`. It is safe to run again after
adding more documents.

Excel files such as nomenclature subsets are stored in `data/raw/` and
registered in `data/provenance.csv`; the PDF extractor does not convert Excel
files into text.

### Week 1: prepare and clean the collected data

The Week 1 preparation step works only on the collected corpus. It does not
build embeddings, a vector database, a knowledge graph, or an LLM agent.

Run both preparation scripts from the project root:

```powershell
.\.venv\Scripts\python.exe src\extract\prepare.py
.\.venv\Scripts\python.exe src\normalize\nomenclature.py
```

`src/extract/prepare.py` cleans extracted text by:

- normalizing Unicode characters and whitespace;
- removing control characters, URLs, repeated headers, and footers;
- detecting very short, low-quality, or duplicate documents;
- filling missing metadata from `data/provenance.csv` or from the document;
- normalizing drug names and converting detected mass doses to mg;
- flagging unusual document lengths and dose values for review.

`src/normalize/nomenclature.py` prepares `data/medicaments_40.xlsx` by:

- removing empty rows and trimming missing text cells;
- removing rows without a drug name or DCI;
- creating normalized DCI names without accents;
- creating canonical medicine keys from DCI, dosage, and pharmaceutical form;
- reporting missing values and duplicate rows.

`src/normalize/normalizer.py` resolves a query against the nomenclature table.
It supports exact DCI, brand, and ATC matches, typo-tolerant matching, and
explicit `ambiguous` or `unknown` results instead of silently choosing a
medicine.

The scripts create the following Week 1 outputs:

| Output | Purpose |
|---|---|
| `data/text_clean/` | Cleaned text documents; raw files in `data/raw/` and extracted files in `data/text/` are not modified |
| `data/clean_docs.csv` | Document metadata, quality indicators, detected doses, and outlier flags |
| `data/rejected.csv` | Documents rejected because they are too short, corrupted, or duplicates |
| `data/medicaments_clean.csv` | Cleaned and normalized nomenclature table |
| `reports/week1_prep_report.json` | Summary of documents kept/rejected and quality flags |

Dose and length outliers are reported rather than automatically deleting
medical content: a document can legitimately contain several therapeutic
dosages. The flags should be reviewed before any later retrieval step.

## Libraries (all installed by `requirements.txt`)

| Library | Used for |
|---|---|
| `requests` | Calling the Groq API and downloading documents |
| `python-dotenv` | Reading the key from `.env` |
| `pandas`, `openpyxl` | Reading the teacher's Excel list and CSV files |
| `beautifulsoup4` | Parsing saved web pages (HTML) |
| `pymupdf` | Reading PDFs (notices, RCP, ANSM table) |
| `rank_bm25` | Keyword search (BM25) |
| `rapidfuzz` | Matching drug names with typos |
| `streamlit` | The web interface |

The Streamlit app currently uses local lexical retrieval over `data/text_clean/`
(falling back to `data/text/`). It sends the top matching excerpts, not the
whole corpus, to the Groq LLM. Set `GROQ_API_KEY` in `.env` before asking a
question.

## Current question-answering workflow

Run the Streamlit application from the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app\app.py
```

For each question, DawaCheck:

1. searches the local cleaned text files;
2. selects the most relevant excerpts;
3. sends only those excerpts and the question to Groq;
4. instructs the model to answer only from the provided sources;
5. displays clickable links to the official source URLs associated with the
   retrieved documents.

The interface displays the official URLs recorded in `data/provenance.csv` for
the retrieved sources. The expected answer is never sent to the model; it is
used only by the evaluation script to compare required facts with the model
answer.

## Evaluation and comparison

Set `QID` in `tests/run_eval.py` to one of the IDs in
`tests/test_questions.json`, then run:

```powershell
.\.venv\Scripts\python.exe tests\run_eval.py
```

The evaluator writes:

| Output | Purpose |
|---|---|
| `tests/results_week1.csv` | Semicolon-separated comparison data |
| `tests/results_week1.xlsx` | Excel comparison with separate columns |

The comparison includes the expected answer, LLM answer, matched facts,
missing facts, factual coverage percentage, and verdict (`correct`,
`partial`, or `wrong`).

Each run asks the selected question three times and records three
sub-question rows per run.


## Safety

This project is for information retrieval and evaluation only. It is not a
substitute for a doctor, pharmacist, or official product information. Answers
must cite their source documents and should direct users to a qualified
healthcare professional for diagnosis, dosage changes, interactions, or
emergency symptoms.

