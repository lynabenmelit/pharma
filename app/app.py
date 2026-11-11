"""Streamlit entry point for DawaCheck."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_pipeline():
    """Load the numbered pipeline module without requiring package renaming."""
    module_path = Path(__file__).with_name("4_rag_pipeline.py")
    spec = importlib.util.spec_from_file_location("rag_pipeline", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load pipeline from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    """Render the DawaCheck interface."""
    import streamlit as st

    st.set_page_config(page_title="DawaCheck", page_icon="💊")
    st.title("DawaCheck")
    st.caption("Evidence-grounded medicine information assistant")
    question = st.text_area("Ask a question about a medicine")
    if st.button("Search") and question.strip():
        pipeline = load_pipeline()
        st.info(pipeline.answer_question(question, []))


if __name__ == "__main__":
    main()
