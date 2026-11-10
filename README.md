# DawaCheck

DawaCheck is a local-first medicine-information assistant. It is designed to
download trusted medicine documents, extract structured information, normalize
medicine names, and answer questions with retrieval-augmented generation.

## Project structure

```text
DawaCheck/
├── .env
├── .gitignore
├── README.md
├── data/
│   ├── raw/
│   ├── processed/
│   └── vector_db/
├── src/
│   ├── 1_scraper.py
│   ├── 2_extractor.py
│   ├── 3_normalizer.py
│   ├── 4_rag_pipeline.py
│   └── app.py
└── tests/
    └── test_questions.json
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

## Safety

This project is for information retrieval and evaluation only. It is not a
substitute for a doctor, pharmacist, or official product information. Answers
must cite their source documents and should direct users to a qualified
healthcare professional for diagnosis, dosage changes, interactions, or
emergency symptoms.

