"""Local retrieval and answer-generation boundary for DawaCheck."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from src.llm import ask
from src.search.bm25 import retrieve_bm25
from src.search.semantic import retrieve_semantic
from src.verify.citations import verify_citations


ROOT = Path(__file__).resolve().parents[2]
MAX_CONTEXT_CHARS = 12000


@dataclass(frozen=True)
class SourceDocument:
    """A retrieved source excerpt used to ground an answer."""

    title: str
    content: str
    source: str
    official_url: str = ""


def _source_urls() -> dict[str, str]:
    provenance = ROOT / "data" / "provenance.csv"
    try:
        with provenance.open(encoding="utf-8", newline="") as handle:
            return {
                Path(row["text_path"]).name: row["url"]
                for row in csv.DictReader(handle)
                if row.get("text_path") and row.get("url")
            }
    except (OSError, UnicodeError, KeyError) as error:
        raise RuntimeError(f"Could not read source metadata {provenance}") from error


def _retrieve_candidates(
    question: str,
    top_k: int,
    mode: str,
    bm25_weight: float = 0.5,
) -> list[dict[str, object]]:
    """Retrieve candidates using one of the supported retrieval modes."""
    normalized_mode = mode.lower()
    if normalized_mode not in {"bm25", "semantic", "hybrid"}:
        raise ValueError(
            "mode must be one of: 'bm25', 'semantic', or 'hybrid'"
        )
    if not 0.0 <= bm25_weight <= 1.0:
        raise ValueError("bm25_weight must be between 0 and 1")

    candidate_count = top_k * 5
    if normalized_mode == "bm25":
        return retrieve_bm25(question, top_k=candidate_count)
    if normalized_mode == "semantic":
        return retrieve_semantic(question, top_k=candidate_count)

    bm25_candidates = retrieve_bm25(question, top_k=candidate_count)
    semantic_candidates = retrieve_semantic(question, top_k=candidate_count)

    def normalize(candidates: list[dict[str, object]]) -> dict[str, float]:
        if not candidates:
            return {}
        scores = [float(candidate["score"]) for candidate in candidates]
        minimum = min(scores)
        maximum = max(scores)
        score_range = maximum - minimum
        if score_range == 0:
            return {
                str(candidate["id"]): 1.0
                for candidate in candidates
            }
        return {
            str(candidate["id"]): (float(candidate["score"]) - minimum) / score_range
            for candidate in candidates
        }

    bm25_scores = normalize(bm25_candidates)
    semantic_scores = normalize(semantic_candidates)
    hybrid_scores: dict[str, float] = {}
    candidate_by_id: dict[str, dict[str, object]] = {}
    for candidate in bm25_candidates:
        candidate_id = str(candidate["id"])
        candidate_by_id.setdefault(candidate_id, candidate)
        hybrid_scores[candidate_id] = (
            bm25_weight * bm25_scores.get(candidate_id, 0.0)
            + (1.0 - bm25_weight) * semantic_scores.get(candidate_id, 0.0)
        )
    for candidate in semantic_candidates:
        candidate_id = str(candidate["id"])
        candidate_by_id.setdefault(candidate_id, candidate)
        hybrid_scores[candidate_id] = (
            bm25_weight * bm25_scores.get(candidate_id, 0.0)
            + (1.0 - bm25_weight) * semantic_scores.get(candidate_id, 0.0)
        )

    ranked_ids = sorted(
        hybrid_scores,
        key=lambda candidate_id: hybrid_scores[candidate_id],
        reverse=True,
    )
    ranked_candidates = []
    for candidate_id in ranked_ids:
        candidate = dict(candidate_by_id[candidate_id])
        candidate["hybrid_score"] = hybrid_scores[candidate_id]
        ranked_candidates.append(candidate)
    return ranked_candidates


def retrieve_documents(
    question: str,
    top_k: int = 4,
    mode: str = "bm25",
    bm25_weight: float = 0.5,
) -> list[SourceDocument]:
    """Retrieve the most relevant local text excerpts for a question."""
    source_urls = _source_urls()
    candidates = _retrieve_candidates(question, top_k, mode, bm25_weight)
    selected: list[SourceDocument] = []
    selected_resources: set[str] = set()
    for candidate in candidates:
        source = candidate["source"]
        title = Path(source).name
        document = SourceDocument(
            title=title,
            content=candidate["text"],
            source=source,
            official_url=source_urls.get(title, ""),
        )
        resource_key = document.title
        if resource_key in selected_resources:
            continue
        selected_resources.add(resource_key)
        selected.append(document)
        if len(selected) == top_k:
            break
    return selected


def build_context(documents: list[SourceDocument]) -> str:
    """Format retrieved documents as a bounded model context."""
    context = "\n\n".join(
        f"Source: {document.title} ({document.official_url or document.source})\n"
        f"{document.content}"
        for document in documents
    )
    return context[:MAX_CONTEXT_CHARS]


def _must_refuse_personal_request(question: str) -> bool:
    normalized = question.casefold()
    herbal_terms = (
        "ginseng",
        "complément alimentaire",
        "complement alimentaire",
        "plante médicinale",
        "plante medicinale",
        "herbal supplement",
    )
    personal_medication_terms = (
        "quel médicament prendre",
        "quel medicament prendre",
        "que prendre",
        "puis-je prendre",
        "peux-je prendre",
        "mes douleurs",
        "mon traitement",
        "should i take",
        "what should i take",
        "can i take",
    )
    if any(term in normalized for term in herbal_terms + personal_medication_terms):
        return True

    arabic_allergy_question = (
        any(term in normalized for term in ("حساسية", "حساسيه", "حسيسة"))
        and any(term in normalized for term in ("مريض", "يمكنه", "هل يمكن"))
    )
    return arabic_allergy_question


def answer_question(
    question: str,
    documents: list[SourceDocument] | None = None,
    run: int = 0,
    temperature: float = 0.3,
    mode: str = "bm25",
    bm25_weight: float = 0.5,
) -> str:
    """Answer a question using retrieved local source excerpts."""
    if not question.strip():
        raise ValueError("Question must not be empty.")
    if _must_refuse_personal_request(question):
        if any("\u0600" <= character <= "\u06ff" for character in question):
            return (
                "لا أستطيع التوصية بدواء أو تأكيد ملاءمته لشخص لديه أعراض أو "
                "حساسية أو يتناول علاجًا. يُرجى استشارة طبيب أو صيدلي."
            )
        return (
            "Je ne peux pas recommander un médicament ni confirmer qu'il convient "
            "à une personne selon ses symptômes, allergies ou traitements. "
            "Demandez conseil à un médecin ou à un pharmacien avant de prendre "
            "un médicament ou un complément."
        )
    if documents is None:
        documents = retrieve_documents(
            question,
            mode=mode,
            bm25_weight=bm25_weight,
        )
    if not documents:
        return "No source documents were retrieved. Please add trusted documents first."
    prompt = f"""Réponds à la question uniquement à partir des sources locales ci-dessous.
Si les sources ne contiennent pas l'information, dis-le clairement et n'invente pas.
Cite uniquement les noms de fichiers présents dans la section Sources locales.
Utilise exactement la forme [nom_du_fichier].

Question : {question}

Sources locales :
{build_context(documents)}
"""
    answer = ask(
        prompt,
        system=(
            "Tu es un assistant pharmaceutique prudent. "
            "Tu utilises exclusivement le contexte fourni, tu signales les limites "
            "et tu ne cites aucun fichier absent du contexte."
        ),
        run=run,
        temperature=temperature,
    )
    verification = verify_citations(answer, documents)
    if verification["unsupported"]:
        names = ", ".join(verification["unsupported"])
        answer = (
            f"{answer}\n\n"
            f"Vérification des citations : citation(s) non trouvée(s) dans les "
            f"passages retrouvés — {names}."
        )
    return answer

