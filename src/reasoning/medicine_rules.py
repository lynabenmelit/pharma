"""Medicine graph resolution and equivalence rules."""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
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


SEVERITY = {"CI": 4, "AD": 3, "PE": 2, "APEC": 1}
LEVEL_LABEL = {
    "CI": "Contre-indication",
    "AD": "Association déconseillée",
    "PE": "Précaution d'emploi",
    "APEC": "À prendre en compte",
}
NOT_FOUND = (
    "Non trouvé dans nos sources. L'absence d'information ne prouve pas "
    "l'absence de risque : consultez le RCP et un professionnel de santé."
)


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode(
        "ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


@dataclass(frozen=True)
class Finding:
    kind: str  # "interaction" or "contraindication"
    level: str  # CI / AD / PE / APEC, empty for a contraindication
    subject: str
    object: str
    class_level: bool
    source_file: str
    passage: str
    authority_level: str


@dataclass(frozen=True)
class RuleAnswer:
    status: str  # found | not_found_in_sources | unknown_medicine
    message: str
    findings: tuple[Finding, ...] = field(default_factory=tuple)


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
        self.interaction_rows: list[dict[str, str]] = []
        self.contraindication_rows: list[dict[str, str]] = []
        self.known_ids: set[str] = set()
        self._load_triples()

    def _load_triples(self) -> None:
        vocab_path = self.triples_path.with_name("vocab.csv")
        brand_labels: dict[str, str] = {}
        if vocab_path.is_file():
            with vocab_path.open(encoding="utf-8-sig", newline="") as vocab_file:
                for row in csv.DictReader(vocab_file):
                    if row["kind"].strip() == "entity" and row["name"].startswith("medicament_"):
                        brand_labels[row["name"].strip(
                        )] = row["description"].strip()

        with self.triples_path.open(encoding="utf-8-sig", newline="") as triples_file:
            for row in csv.DictReader(triples_file):
                subject = row["subject"].strip()
                relation = row["relation"].strip()
                obj = row["object"].strip()
                self.known_ids.update((subject, obj))

                if relation == "brand_of":
                    normalized_label = self._normalize_brand_label(
                        brand_labels.get(
                            subject, subject.removeprefix("medicament_"))
                    )
                    brand_drugs = self.brand_to_drug.setdefault(
                        normalized_label, ())
                    if (subject, obj) not in brand_drugs:
                        self.brand_to_drug[normalized_label] = brand_drugs + \
                            (subject + "|" + obj,)
                elif relation == "belongs_to":
                    classes = self.drug_to_classes.setdefault(subject, ())
                    if obj not in classes:
                        self.drug_to_classes[subject] = classes + (obj,)
                elif relation.startswith("interacts_with:"):
                    self.interaction_rows.append(row)
                elif relation == "contraindicated_in":
                    self.contraindication_rows.append(row)

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
            normalized_dci = drug_id.removeprefix(
                "active_ingredient_").replace("_", " ")
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
            normalized = name.removeprefix(
                "active_ingredient_").replace("_", " ")
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
            suffix = normalize_name(drug_id.removeprefix(
                "active_ingredient_").replace("_", " "))
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

    # ---- Week 4 rules: interactions, contraindications, explicit not-found ----

    def _ingredient_ids(self, name: str) -> set[str]:
        direct = f"active_ingredient_{_slug(name)}"
        if direct in self.known_ids:
            return {direct}
        result = self.resolve_brand_to_drug(name)
        if result.status == "matched" and result.drug_id:
            return {result.drug_id}
        return set()

    def _endpoints(self, ingredient_id: str) -> set[str]:
        return {ingredient_id} | set(self.drug_to_classes.get(ingredient_id, ()))

    def check_interaction(self, name_a: str, name_b: str) -> RuleAnswer:
        """Direct or class-level interaction, highest severity first.
        A missing path is 'not found in our sources', never 'safe'."""
        ids_a, ids_b = self._ingredient_ids(
            name_a), self._ingredient_ids(name_b)
        unknown = [n for n, ids in (
            (name_a, ids_a), (name_b, ids_b)) if not ids]
        if unknown:
            return RuleAnswer(
                "unknown_medicine",
                "Médicament non trouvé dans nos sources : " +
                ", ".join(unknown) + ".",
            )
        findings: list[Finding] = []
        for ia in ids_a:
            for ib in ids_b:
                ends_a, ends_b = self._endpoints(ia), self._endpoints(ib)
                for row in self.interaction_rows:
                    s, o = row["subject"].strip(), row["object"].strip()
                    if (s in ends_a and o in ends_b) or (s in ends_b and o in ends_a):
                        findings.append(Finding(
                            "interaction", row["relation"].split(":", 1)[
                                1], s, o,
                            s.startswith("therapeutic_class_") or o.startswith(
                                "therapeutic_class_"),
                            row["source_file"], row["passage"], row["authority_level"]))
        if not findings:
            return RuleAnswer("not_found_in_sources", NOT_FOUND)
        findings.sort(key=lambda f: -SEVERITY.get(f.level, 0))
        top = findings[0]
        return RuleAnswer(
            "found",
            f"{LEVEL_LABEL.get(top.level, top.level)} ({top.subject} / {top.object}).",
            tuple(findings),
        )

    def check_contraindications(self, product_name: str) -> RuleAnswer:
        """Only the named product/form; never generalised to other formulations."""
        key = f"medicament_{_slug(product_name)}"
        findings = tuple(
            Finding("contraindication", "", r["subject"].strip(), r["object"].strip(),
                    False, r["source_file"], r["passage"], r["authority_level"])
            for r in self.contraindication_rows
            if r["subject"].strip() == key or r["subject"].strip().startswith(key + "_")
        )
        if not findings:
            return RuleAnswer("not_found_in_sources", NOT_FOUND)
        products = sorted({f.subject for f in findings})
        return RuleAnswer(
            "found",
            f"{len(findings)} contre-indication(s) dans nos sources pour : " +
            ", ".join(products) + ".",
            findings,
        )
