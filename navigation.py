"""Single Streamlit navigation entrypoint for the BigBrain workflows."""
from __future__ import annotations

from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent
PAGES = ("volume_viewer.py", "pages/1_Validation.py")
LOGO = ROOT / "assets" / "bigbrain-tissuelink-logo.png"


def validate_pages(root: Path = ROOT) -> None:
    missing = [page for page in PAGES if not (root / page).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing navigation page(s): {missing}")


validate_pages()
st.set_page_config(page_title="BigBrain TissueLink", layout="wide")
if LOGO.is_file():
    st.logo(str(LOGO))

explorer = st.Page("volume_viewer.py", title="MRI–Histology Explorer", icon="🧠")
alignment = st.Page("pages/1_Validation.py", title="Alignment review (advanced)", icon="🔎")
st.navigation([explorer, alignment], position="sidebar").run()
