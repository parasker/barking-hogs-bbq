import streamlit as st
from utils import sidebar_logo, app_navigation

import Home
import bbq_intake
import bbq_results_app
import migration_tool

st.set_page_config(page_title="BBQ Tracker", layout="wide")

sidebar_logo()
page = app_navigation()

if page == "Home":
    Home.render()
elif page == "Migration Tool":
    migration_tool.render()
elif page == "Intake Form":
    bbq_intake.render()
elif page == "Results Dashboard":
    bbq_results_app.render()
