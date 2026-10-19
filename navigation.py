"""Single Streamlit navigation entrypoint for the BigBrain workflows."""
from __future__ import annotations

from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent
PAGES = ("volume_viewer.py", "pages/1_Validation.py", "pages/2_Experimental_ROI.py")
LOGO = ROOT / "assets" / "bigbrain-tissuelink-logo-cropped.png"
LOGO_ICON = ROOT / "assets" / "bigbrain-tissuelink-icon.png"


def validate_pages(root: Path = ROOT) -> None:
    missing = [page for page in PAGES if not (root / page).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing navigation page(s): {missing}")


validate_pages()
st.set_page_config(page_title="BigBrain TissueLink", layout="wide")
if LOGO.is_file():
    st.logo(str(LOGO), size="large", icon_image=str(LOGO_ICON) if LOGO_ICON.is_file() else None)

st.markdown(
    """
    <style>
    [data-testid="stSidebarHeader"] img,
    [data-testid="stLogo"] {
        height: 3.75rem;
        max-width: 100%;
        width: auto;
    }
    [data-testid="stSidebarHeader"] {
        padding-top: 1.5rem;
        padding-bottom: 1rem;
    }
    [data-testid="stMainBlockContainer"] {
        padding-top: 2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

explorer = st.Page("volume_viewer.py", title="MRI–Histology Explorer", icon="🧠")
roi = st.Page("pages/2_Experimental_ROI.py", title="Experimental template ROI", icon="🎯")
alignment = st.Page("pages/1_Validation.py", title="Alignment review (advanced)", icon="🔎")
st.navigation([explorer, roi, alignment], position="sidebar").run()
