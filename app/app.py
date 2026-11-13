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
            for document in documents:
                source_path = (pipeline.ROOT / document.source).resolve()
                source_uri = source_path.as_uri()
                st.markdown(
                    f"- [{document.title}]({source_uri})  \n"
                    f"  Lien : `{source_uri}`"
                )


if __name__ == "__main__":
    main()
