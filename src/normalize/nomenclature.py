"""Clean medicaments_40.xlsx: missing values, duplicates, name + dose normalization, outliers.

Column names in the Excel are guessed by keyword (nom/denomination, dci, dosage, forme...),
so it works even if the headers differ slightly. Run:  python src/normalize/nomenclature.py
"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from src import prep_config as config
from src.normalize.normalizer import MedicineRecord
from src.normalize.units import dose_to_mg, norm_name


def _slug(c) -> str:
    return norm_name(c).replace(" ", "_")


def _find(cols, *keywords):
    for k in keywords:
        for c in cols:
            if k in c:
                return c
    return None


def clean_nomenclature(df: pd.DataFrame):
    df = df.copy()
    df.columns = [_slug(c) for c in df.columns]
    rep = {"rows_in": len(df)}

    df = df.dropna(how="all")                                         # empty rows
    for c in df.select_dtypes(include=["object", "string"]):          # trim + empty -> NaN
        df[c] = df[c].astype("string").str.strip().replace("", pd.NA)

    name_c = _find(df.columns, "nom", "denomination", "marque", "name")
    dci_c = _find(df.columns, "dci", "inn", "substance")
    dose_c = _find(df.columns, "dosage", "dose")
    atc_c = _find(df.columns, "atc", "code_atc")
    form_c = _find(df.columns, "forme", "form", "pharmaceutical_form")

    # missing values: report them, and drop rows that have neither a brand nor a DCI
    rep["missing_per_column"] = {c: int(n) for c, n in df.isna().sum().items() if n}
    key = [c for c in (name_c, dci_c) if c]
    if key:
        df = df.dropna(subset=key, how="all")

    # name normalization (brand vs DCI)
    for c in key:
        df[f"{c}_norm"] = df[c].map(norm_name)
    if dci_c and name_c:                                              # fill a missing DCI from nothing = no; flag it
        df["dci_missing"] = df[dci_c].isna().astype(int)

    # dose -> mg, outliers, min-max scale
    if dose_c:
        df["dosage_mg"] = df[dose_c].map(dose_to_mg)
        rep["dose_unparsed"] = int(df["dosage_mg"].isna().sum())
        v = df["dosage_mg"].dropna()
        cap = config.MAX_DOSE_MG
        if len(v) >= 8:                                               # MAD rule when enough data
            med = statistics.median(v)
            mad = statistics.median(abs(x - med) for x in v) or 1.0
            df["dose_outlier"] = ((df["dosage_mg"] - med).abs() / mad > 10).astype(int)
        else:                                                         # tiny list: absolute cap
            df["dose_outlier"] = ((df["dosage_mg"] > cap) | (df["dosage_mg"] <= 0)).astype(int)
        rng = v.max() - v.min() if len(v) else 0
        df["dosage_scaled"] = (df["dosage_mg"] - v.min()) / rng if rng else 0.0
        rep["dose_outliers"] = int(df["dose_outlier"].sum())

    if form_c:
        df["form_norm"] = df[form_c].map(norm_name)
    if atc_c:
        df["atc_norm"] = df[atc_c].map(norm_name)
    if dci_c:
        def canonical_key(row):
            dosage = row.get("dosage_mg")
            form = row.get("form_norm", "")
            return MedicineRecord(str(row[dci_c]), dosage_mg=None if pd.isna(dosage) else float(dosage), form=str(form)).canonical_key

        df["canonical_key"] = df.apply(canonical_key, axis=1)

    n = len(df)
    df = df.drop_duplicates(subset=[c for c in df.columns if c != "dci_missing"])
    rep["duplicates_removed"] = n - len(df)
    rep["rows_out"] = len(df)
    return df, rep


def main():
    df, rep = clean_nomenclature(pd.read_excel(config.NOMENCLATURE_XLSX))
    df.to_csv(config.NOMENCLATURE_CLEAN_CSV, index=False, encoding="utf-8")
    print(rep)


if __name__ == "__main__":
    main()
