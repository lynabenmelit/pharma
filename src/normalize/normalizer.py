"""Resolve medicine names, ATC codes, and aliases to canonical records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd
from rapidfuzz import fuzz, process

from src.normalize.units import norm_name

MatchStatus = Literal["matched", "ambiguous", "unknown"]


def normalize_name(name: object) -> str:
    """Return a stable comparison form for a medicine name or identifier."""
    return norm_name(name)


@dataclass(frozen=True)
class MedicineRecord:
    """Canonical medicine identity and optional product attributes."""

    dci: str
    atc: str = ""
    brand: str = ""
    dosage_mg: float | None = None
    form: str = ""

    @property
    def canonical_key(self) -> str:
        """Build the equivalence key required for same-product matching."""
        dosage = "" if self.dosage_mg is None else f"{self.dosage_mg:g}"
        return "|".join((normalize_name(self.dci), dosage, normalize_name(self.form)))

    @property
    def aliases(self) -> tuple[str, ...]:
        values = (self.dci, self.atc, self.brand)
        return tuple(value for value in (normalize_name(v) for v in values) if value)


@dataclass(frozen=True)
class MatchResult:
    """Explicit result of resolving a user-supplied medicine identifier."""

    status: MatchStatus
    query: str
    record: MedicineRecord | None = None
    candidates: tuple[MedicineRecord, ...] = ()
    score: float | None = None


def normalize_record(record: dict[str, object]) -> dict[str, object]:
    """Normalize textual medicine identifiers while preserving other fields."""
    normalized = dict(record)
    for field in ("name", "dci", "atc", "brand", "form"):
        if field in normalized and normalized[field] is not None:
            normalized[field] = normalize_name(normalized[field])
    return normalized


class MedicineResolver:
    """Match exact aliases first, then typo-tolerant fuzzy candidates."""

    def __init__(
        self,
        records: list[MedicineRecord],
        *,
        score_cutoff: float = 85,
        ambiguity_margin: float = 5,
    ) -> None:
        self.records = tuple(records)
        self.score_cutoff = score_cutoff
        self.ambiguity_margin = ambiguity_margin
        self._aliases: dict[str, tuple[MedicineRecord, ...]] = {}
        for record in self.records:
            for alias in record.aliases:
                existing = self._aliases.get(alias, ())
                if record not in existing:
                    self._aliases[alias] = existing + (record,)
        self._choices = tuple(self._aliases)

    @classmethod
    def from_dataframe(cls, frame: pd.DataFrame, **kwargs: object) -> "MedicineResolver":
        """Build a resolver from a cleaned or raw nomenclature dataframe."""
        columns = {normalize_name(column).replace(" ", "_"): column for column in frame.columns}

        def find(*names: str) -> object | None:
            for name in names:
                if name in columns:
                    return columns[name]
            return None

        dci_column = find("dci", "dci_nom_de_la_substance", "inn", "substance")
        if dci_column is None:
            raise ValueError("Nomenclature data must contain a DCI/substance column")
        atc_column = find("atc", "code_atc", "code_atc_indicatif")
        brand_column = find("brand", "marque", "nom", "denomination", "name")
        dose_column = find("dosage_mg", "dosage", "dose")
        form_column = find("form", "forme", "pharmaceutical_form")

        records: list[MedicineRecord] = []
        for _, row in frame.iterrows():
            dci = row[dci_column]
            if pd.isna(dci) or not normalize_name(dci):
                continue
            dosage = row[dose_column] if dose_column is not None else None
            if dosage is not None and pd.isna(dosage):
                dosage = None
            records.append(
                MedicineRecord(
                    dci=str(dci),
                    atc="" if atc_column is None or pd.isna(row[atc_column]) else str(row[atc_column]),
                    brand="" if brand_column is None or pd.isna(row[brand_column]) else str(row[brand_column]),
                    dosage_mg=float(dosage) if dosage is not None else None,
                    form="" if form_column is None or pd.isna(row[form_column]) else str(row[form_column]),
                )
            )
        return cls(records, **kwargs)

    def resolve(self, query: object) -> MatchResult:
        """Resolve a query without silently selecting an ambiguous candidate."""
        raw_query = "" if query is None else str(query)
        normalized_query = normalize_name(raw_query)
        if not normalized_query:
            return MatchResult("unknown", raw_query)

        exact = self._aliases.get(normalized_query, ())
        if len(exact) == 1:
            return MatchResult("matched", raw_query, exact[0], exact, 100.0)
        if len(exact) > 1:
            return MatchResult("ambiguous", raw_query, candidates=exact, score=100.0)

        matches = process.extract(
            normalized_query,
            self._choices,
            scorer=fuzz.ratio,
            score_cutoff=self.score_cutoff,
            limit=3,
        )
        if not matches:
            return MatchResult("unknown", raw_query)

        best_alias, best_score, _ = matches[0]
        candidates = self._aliases[best_alias]
        second_score = matches[1][1] if len(matches) > 1 else None
        if second_score is not None and best_score - second_score < self.ambiguity_margin:
            ambiguous = []
            for alias, score, _ in matches:
                if best_score - score < self.ambiguity_margin:
                    ambiguous.extend(self._aliases[alias])
            return MatchResult("ambiguous", raw_query, candidates=tuple(dict.fromkeys(ambiguous)), score=best_score)
        if len(candidates) != 1:
            return MatchResult("ambiguous", raw_query, candidates=candidates, score=best_score)
        return MatchResult("matched", raw_query, candidates[0], candidates, best_score)
