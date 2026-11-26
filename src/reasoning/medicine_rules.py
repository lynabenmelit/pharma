"""Medicine graph resolution and equivalence rules."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from src.normalize.normalizer import MedicineRecord, MedicineResolver, normalize_name


@dataclass(frozen=True)
class R1Result:
    status: str
    drug_id: str = ""
    dci: str = ""
    message: str = ""


@dataclass(frozen=True)
class R4Result:
    same_dci: bool
    same_class: bool
    shared_classes: tuple[str, ...] = ()


class MedicineRules:
    """Apply brand resolution and drug-equivalence rules."""

    def __init__(
        self,
        resolver: MedicineResolver,
        triples_path: str | Path,
    ) -> None:
        self.resolver = resolver
        self.triples_path = Path(triples_path)
        self.brand_to_drug: dict[str, tuple[str, ...]] = {}
        self.drug_to_classes: dict[str, tuple[str, ...]] = {}
        self.drug_to_dci: dict[str, str] = {}
        self._load_triples()

    def _load_triples(self) -> None:
        vocab_path = self.triples_path.with_name("vocab.csv")
        brand_labels: dict[str, str] = {}
        if vocab_path.is_file():
            with vocab_path.open(encoding="utf-8-sig", newline="") as vocab_file:
                for row in csv.DictReader(vocab_file):
                    if row["kind"].strip() == "entity" and row["name"].startswith("medicament_"):
                        brand_labels[row["name"].strip()] = row["description"].strip()

        with self.triples_path.open(encoding="utf-8-sig", newline="") as triples_file:
            for row in csv.DictReader(triples_file):
                subject = row["subject"].strip()
                relation = row["relation"].strip()
                obj = row["object"].strip()

                if relation == "brand_of":
                    normalized_label = self._normalize_brand_label(
                        brand_labels.get(subject, subject.removeprefix("medicament_"))
                    )
                    brand_drugs = self.brand_to_drug.setdefault(normalized_label, ())
                    if (subject, obj) not in brand_drugs:
                        self.brand_to_drug[normalized_label] = brand_drugs + (subject + "|" + obj,)
                elif relation == "belongs_to":
                    classes = self.drug_to_classes.setdefault(subject, ())
                    if obj not in classes:
                        self.drug_to_classes[subject] = classes + (obj,)

    @staticmethod
    def _normalize_brand_label(label: str) -> str:
        return normalize_name(label)

    def resolve_brand_to_drug(self, name: str) -> R1Result:
        """Rule R1: resolve a brand/unknown name to one DCI, stopping on uncertainty."""
        normalized_name = self._normalize_brand_label(name)
        brand_matches = self.brand_to_drug.get(normalized_name, ())
        if len(brand_matches) > 1:
            return R1Result("ambiguous", message=f"Ambiguous medicine name: {name}")
        if len(brand_matches) == 1:
            brand_id, drug_id = brand_matches[0].split("|", 1)
            record = self._record_for(drug_id)
            if record is not None:
                return R1Result("matched", drug_id, record.dci)
            normalized_dci = drug_id.removeprefix("active_ingredient_").replace("_", " ")
            return R1Result("matched", drug_id, normalized_dci)

        match = self.resolver.resolve(name)
        if match.status == "unknown":
            return R1Result("unknown", message=f"Unknown medicine name: {name}")
        if match.status == "ambiguous":
            return R1Result("ambiguous", message=f"Ambiguous medicine name: {name}")

        record = match.record
        if record is None:
            return R1Result("unknown", message=f"Unknown medicine name: {name}")

        drug_ids = tuple(
            drug_id
            for drug_id, dci in self.drug_to_dci.items()
            if dci.lower() == record.dci.lower()
        )
        if not drug_ids:
            normalized_dci = record.dci.lower().replace(" ", "_").replace("-", "_")
            drug_ids = (f"active_ingredient_{normalized_dci}",)

        return R1Result("matched", drug_ids[0], record.dci)

    def resolve_drug_names(self, names: list[str]) -> list[R1Result]:
        """Resolve every requested name; no result is inferred after an unknown/ambiguous name."""
        results: list[R1Result] = []
        for name in names:
            result = self.resolve_brand_to_drug(name)
            results.append(result)
            if result.status != "matched":
                break
        return results

    def rule_r4(self, left: str, right: str) -> R4Result:
        """Rule R4: flag drugs with the same DCI or an overlapping therapeutic class."""
        left_record = self._record_for(left)
        right_record = self._record_for(right)

        same_dci = (
            left_record is not None
            and right_record is not None
            and normalize_name(left_record.dci) == normalize_name(right_record.dci)
        )
        left_classes = set(self.drug_to_classes.get(self._drug_id(left), ()))
        right_classes = set(self.drug_to_classes.get(self._drug_id(right), ()))
        shared_classes = tuple(sorted(left_classes & right_classes))
        return R4Result(same_dci, bool(shared_classes), shared_classes)

    def _record_for(self, name: str) -> MedicineRecord | None:
        if name.startswith("active_ingredient_"):
            normalized = name.removeprefix("active_ingredient_").replace("_", " ")
            for record in self.resolver.records:
                if record.dci.lower().replace("-", " ") == normalized.lower().replace("-", " "):
                    return record
        result = self.resolver.resolve(name)
        return result.record if result.status == "matched" else None

    def _drug_id(self, name: str) -> str:
        normalized_name = normalize_name(name)
        for brand_name, brand_matches in self.brand_to_drug.items():
            if normalize_name(brand_name) == normalized_name:
                if len(brand_matches) == 1:
                    _, drug_id = brand_matches[0].split("|", 1)
                    return drug_id

        for drug_id in self.drug_to_classes:
            suffix = normalize_name(drug_id.removeprefix("active_ingredient_").replace("_", " "))
            if suffix == normalized_name:
                return drug_id

        result = self.resolve_brand_to_drug(name)
        if result.status == "matched" and result.drug_id:
            return result.drug_id

        record = self._record_for(name)
        if record is not None:
            normalized_dci = normalize_name(record.dci)
            for drug_id in self.drug_to_classes:
                if normalize_name(drug_id.removeprefix("active_ingredient_")) == normalized_dci:
                    return drug_id
        return ""
