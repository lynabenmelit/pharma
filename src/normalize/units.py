"""Name and unit normalization (shared by the text pipeline and the Excel pipeline)."""
import re
import unicodedata

MASS_TO_MG = {"mg": 1.0, "g": 1000.0, "µg": 0.001, "ug": 0.001, "mcg": 0.001}
DOSE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mg|g|µg|ug|mcg|ml|ui|%)(?![a-zA-Z])", re.I)


def norm_name(s) -> str:
    """'Doliprane® 1000' -> 'doliprane 1000' ; 'Paracétamol' -> 'paracetamol'."""
    if s is None or (isinstance(s, float) and s != s):
        return ""
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def extract_doses(text: str):
    """All doses in a text as (value, unit); mass units are converted to mg."""
    out = []
    for v, u in DOSE_RE.findall(text):
        val, u = float(v.replace(",", ".")), u.lower()
        out.append((round(val * MASS_TO_MG[u], 4), "mg") if u in MASS_TO_MG else (val, u))
    return out


def dose_to_mg(cell):
    """'500 mg' / '1 g' / '0,5g' / 500 -> mg as float ; None if not parseable."""
    if cell is None or (isinstance(cell, float) and cell != cell):
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    d = extract_doses(str(cell))
    mg = [v for v, u in d if u == "mg"]
    return mg[0] if mg else None
