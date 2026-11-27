"""Streamlit entry point for DawaCheck."""

from __future__ import annotations

def load_pipeline():
    """Load the local retrieval pipeline."""
    from src.search import rag_pipeline

    return rag_pipeline


def _render_safety_result(st, result) -> None:
    if result["status"] == "unresolved":
        st.warning(
            "I could not confidently resolve both medicine names. "
            "No safety conclusion can be made."
        )
        for medicine in result["medicines"]:
            if medicine["status"] != "matched":
                st.write(medicine["message"])
        return

    medicines = result["medicines"]
    st.caption(
        "Matched medicines: "
        f"{medicines[0]['query']} → {medicines[0]['dci']}; "
        f"{medicines[1]['query']} → {medicines[1]['dci']}."
    )

    if result["same_ingredient"]:
        st.warning(
            "Both names resolve to the same active ingredient. "
            "This lookup does not assess duplicate-dose risk."
        )

    if result["interactions"]:
        st.warning(
            "A matching interaction record was found in the available sources:"
        )
        interaction_labels = {
            "CI": "CI — contre-indication",
            "AD": "AD — association déconseillée",
            "PE": "PE — précaution d'emploi",
            "APEC": "APEC — à prendre en compte",
        }
        for row in result["interactions"]:
            level = row["relation"].partition(":")[2]
            st.markdown(
                f"- **{interaction_labels.get(level, 'Interaction')}:** "
                f"{row['passage']}"
            )
            if row["official_url"]:
                st.markdown(
                    f"  Source: [{row['source_file']}]({row['official_url']})"
                )
            else:
                st.caption(f"Source: {row['source_file']}")
    else:
        st.info(
            "No matching interaction record was found in the current data. "
            "This does not establish that the combination is safe."
        )

    if result["contraindications"]:
        st.subheader("Recorded contraindications for these medicines")
        for row in result["contraindications"]:
            marker = " — pregnancy-related" if row["pregnancy_related"] else ""
            st.markdown(
                f"- **{row['medicine_name']} — {row['condition']}{marker}:** "
                f"{row['passage']}"
            )
            if row["official_url"]:
                st.markdown(
                    f"  Source: [{row['source_file']}]({row['official_url']})"
                )
            else:
                st.caption(f"Source: {row['source_file']}")
    else:
        st.info(
            "No contraindication records were found for these medicines in "
            "the current data. This does not establish that no "
            "contraindications exist."
        )

    st.caption(
        "This lookup does not determine whether a dose, pregnancy stage, or "
        "condition applies to a person. Ask a doctor or pharmacist before "
        "changing treatment."
    )


def main() -> None:
    """Render the DawaCheck interface."""
    import streamlit as st

    st.set_page_config(page_title="DawaCheck", page_icon="💊")
    st.title("DawaCheck")
    st.caption("Evidence-grounded medicine information assistant")

    st.subheader("Check documented medicine warnings")
    st.caption(
        "Limited source lookup only. No matching record does not mean the "
        "combination is safe. Interaction coverage currently contains only "
        "three records. Dose-specific safety is not assessed. "
        "Pregnancy-related contraindications are highlighted when available. "
        "Safety questions in chat naming two recognized medicines use this "
        "same source lookup."
    )
    with st.form("medicine_safety_lookup"):
        first_column, second_column = st.columns(2)
        with first_column:
            first_medicine = st.text_input("First medicine")
        with second_column:
            second_medicine = st.text_input("Second medicine")
        check_submitted = st.form_submit_button("Check available sources")

    if check_submitted:
        from src.graph.safety_lookup import lookup_medicine_pair

        try:
            result = lookup_medicine_pair(
                first_medicine,
                second_medicine,
            )
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
        else:
            _render_safety_result(st, result)

    st.divider()
    mode = st.selectbox(
        "Retrieval mode",
        options=["bm25", "semantic", "hybrid"],
        index=0,
    )
    question = st.text_area("Ask a question about a medicine")
    if st.button("Search") and question.strip():
        from src.graph.safety_lookup import (
            detect_medicine_mentions,
            is_safety_lookup_question,
            lookup_medicine_pair,
        )

        if is_safety_lookup_question(question):
            medicines, ambiguous = detect_medicine_mentions(question)
            if ambiguous:
                st.warning(
                    "I could not confidently identify every medicine in that "
                    "safety question. Use the two medicine fields above."
                )
            elif len(medicines) != 2:
                st.warning(
                    "For safety questions, enter exactly two recognized "
                    "medicine names in the fields above. I won't answer from "
                    "general retrieval sources."
                )
            else:
                try:
                    result = lookup_medicine_pair(*medicines)
                except (RuntimeError, ValueError) as error:
                    st.error(str(error))
                else:
                    _render_safety_result(st, result)
        else:
            pipeline = load_pipeline()
            documents = pipeline.retrieve_documents(question, mode=mode)
            st.info(pipeline.answer_question(question, documents, mode=mode))
            if documents:
                st.subheader("Sources utilisées")
                displayed_urls = set()
                for document in documents:
                    official_url = getattr(document, "official_url", "")
                    if official_url and official_url not in displayed_urls:
                        st.markdown(f"- [{official_url}]({official_url})")
                        displayed_urls.add(official_url)


if __name__ == "__main__":
    main()
