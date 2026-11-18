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
│   │   ├── anpp/
│   │   ├── ansm/
│   │   ├── dailymed/
│   │   ├── dzairPharma/
│   │   └── nomenclature/
│   ├── processed/        # reserved for processed source artifacts
│   ├── text/             # text extracted from PDFs and HTML
│   ├── text_clean/       # cleaned text used by retrieval
│   ├── vector_db/        # reserved for vector indexes
│   ├── chunks.jsonl      # chunked documents with metadata
│   ├── chunks_report.json # chunking statistics
│   ├── clean_docs.csv
│   ├── medicaments_40.xlsx
│   ├── medicaments_clean.csv
│   ├── provenance.csv    # source, URL, date, language, authority level
│   └── rejected.csv
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
├── notebooks/            # notebook workspace
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

## Chunk preparation

Run the chunking script from the project root:

```powershell
.\.venv\Scripts\python.exe src\search\chunk_documents.py
```

The script reads `data/text_clean/` and creates:

| Output | Purpose |
|---|---|
| `data/chunks.jsonl` | One passage per line, with document and source metadata |
| `data/chunks_report.json` | Chunk count and average/largest chunk size |

Chunks are kept below 1500 characters. A 200-character overlap is added
between passages so that nearby context is less likely to be lost.

Each chunk contains:

- a stable chunk identifier and chunk position;
- the source document and source category;
- normalized and original drug names;
- the official source URL;
- the document language and authority level;
- the chunk text.

The current chunking run produced 92 document entries and 3057 chunks.
The average chunk size is 1209.5 characters.

Run this script again whenever documents are added or the cleaned text is
regenerated. It replaces the previous `data/chunks.jsonl` and
`data/chunks_report.json` with a complete index of the current corpus:

```powershell
.\.venv\Scripts\python.exe src\extract\extractor.py
.\.venv\Scripts\python.exe src\extract\prepare.py
.\.venv\Scripts\python.exe src\search\chunk_documents.py
```

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
| `rank_bm25` | BM25 keyword search over prepared chunks |
| `rapidfuzz` | Matching drug names with typos |
| `streamlit` | The web interface |

The Streamlit app uses BM25 keyword retrieval over every chunk in
`data/chunks.jsonl`. The index is tokenized with accent normalization and
returns the highest-scoring chunks, not the whole corpus, to the Groq LLM.
Set `GROQ_API_KEY` in `.env` before asking a question.

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

