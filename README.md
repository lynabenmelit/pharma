# DawaCheck

DawaCheck is a local-first medicine-information assistant. It is designed to
download trusted medicine documents, extract structured information, normalize
medicine names, and answer questions with retrieval-augmented generation.

## Project structure

```text
pharmeazor/
├── README.md
├── .gitignore            # must contain: .env, venv/, __pycache__/
├── .env.example          # GROQ_API_KEY=your_key_here  (no real key)
├── requirements.txt
├── config.py
├── data/
│   ├── raw/              # original PDFs / HTML, never edited
│   ├── text/             # converted text files
│   ├── medicaments_40.xlsx
│   └── provenance.csv    # source, url, date, language, authority level
├── cache/
│   └── llm_cache.json    # saved LLM answers (replay the test set)
├── src/
│   ├── llm.py            # Groq call + cache + retry
│   ├── collect/          # downloading + PDF to text
│   ├── extract/          # sections: indications, contraindications...
│   ├── normalize/        # brand / DCI / ATC matching
│   ├── search/           # BM25 + embeddings
│   ├── reconcile/        # conflicts between sources
│   └── verify/           # number checker
├── app/
│   └── app.py            # Streamlit interface
├── tests/
│   ├── test_questions.csv  # question, expected answer, reference passage
│   └── run_eval.py         # one-click evaluation
├── notebooks/            # Colab notebooks (embeddings)
└── reports/
    ├── week1.md ...      # copies of weekly reports
    └── sources_terms.md  # terms of use + robots.txt of each site
```

## Setup

1. Create a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the dependencies used by your chosen implementation (for example,
   Streamlit, Gemini, a PDF parser, and a vector database).

3. Add your Gemini API key to `.env`:

   ```text
   GEMINI_API_KEY=your_key_here
   ```

4. Put source PDFs and HTML files in `data/raw/`. Generated files belong in
   `data/processed/`, and local vector indexes belong in `data/vector_db/`.

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

Embeddings (E5 or BGE-M3) will be computed in Google Colab, so nothing more to install locally for now.


## Safety

This project is for information retrieval and evaluation only. It is not a
substitute for a doctor, pharmacist, or official product information. Answers
must cite their source documents and should direct users to a qualified
healthcare professional for diagnosis, dosage changes, interactions, or
emergency symptoms.

