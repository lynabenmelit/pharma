"""Streamlit entry point for DawaCheck."""

from __future__ import annotations

def load_pipeline():
    """Load the local retrieval pipeline."""
    from src.search import rag_pipeline

    return rag_pipeline


def main() -> None:
    """Render the DawaCheck interface."""
    import streamlit as st

    st.set_page_config(page_title="DawaCheck", page_icon="💊")
    st.title("DawaCheck")
    st.caption("Evidence-grounded medicine information assistant")
    question = st.text_area("Ask a question about a medicine")
    if st.button("Search") and question.strip():
        pipeline = load_pipeline()
        documents = pipeline.retrieve_documents(question)
        st.info(pipeline.answer_question(question, documents))
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
