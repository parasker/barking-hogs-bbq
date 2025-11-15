import streamlit as st
from pathlib import Path
from base64 import b64encode

MEATS = ["Chicken", "Ribs", "Pork", "Brisket"]

logo_path = Path("bh-logo.png")
def sidebar_logo():
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            logo_base64 = b64encode(f.read()).decode()
    st.sidebar.markdown(
        f"""
        <div style="display:flex; justify-content:center; align-items:center; margin-bottom:1rem;">
            <img src="data:image/png;base64,{logo_base64}" width="180">
        </div>
        """,
        unsafe_allow_html=True
    )
    # st.logo(str(logo_path), size="large", link=None, icon_image=None)

def app_navigation():
    return st.sidebar.radio(
        "Navigate",
        ["Home", "Intake Form", "Migration Tool", "Results Dashboard"]
    )

