"""Reads the PDFs in data/raw/ and writes one .txt per PDF into data/text/.
Never modifies the raw files. Safe to re-run."""
import hashlib, re
from pathlib import Path
try:
    import pymupdf as fitz
except ImportError:
    import fitz  # older versions

RAW = Path("data/raw")
OUT = Path("data/text")
OUT.mkdir(parents=True, exist_ok=True)

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def clean(text):
    text = text.replace("\u00ad", "")                 # invisible soft hyphen
    text = re.sub(r"[ \t]+", " ", text)                # repeated spaces
    text = re.sub(r"\n{3,}", "\n\n", text)             # repeated blank lines
    return text.strip()                                # NEVER change numbers or units

done = {}
for pdf in sorted(RAW.rglob("*.pdf")):
    h = sha256(pdf)
    if h in done:
        print(f"DUPLICATE: {pdf.name} = {done[h]}")
        continue
    done[h] = pdf.name
    with fitz.open(pdf) as doc:
        pages = [clean(p.get_text()) for p in doc]
    out = OUT / (pdf.stem + ".txt")
    out.write_text("\n\n".join(f"[page {i+1}]\n{t}" for i, t in enumerate(pages)), encoding="utf-8")
    n = sum(len(t) for t in pages)
    warn = "  <-- very little text, scanned PDF?" if n < 100 * len(pages) else ""
    print(f"OK: {pdf.name} -> {out.name} ({len(pages)} pages, {n} characters){warn}")