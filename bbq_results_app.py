import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from supabase_client import supabase_get
from utils import sidebar_logo, app_navigation

# def render():
#     st.title("🔥 BBQ Results Dashboard")
#     st.caption("Analyze KCBS competition performance — core meats & ancillary")
#     # --------------------------------------------------
#     # LOAD DATA
#     # --------------------------------------------------
# ---------------------------------------------------
# LOAD ALL TABLES SAFELY
# ---------------------------------------------------
@st.cache_data
def load_all():
    def get_df(table):
        resp = supabase_get(table)
        if resp is None or resp.status_code != 200:
            return pd.DataFrame()
        data = resp.json()
        if isinstance(data, dict):
            return pd.DataFrame([data])
        return pd.DataFrame(data)

    return {
        "events": get_df("competition_events"),
        "years": get_df("competition_years"),
        "meats": get_df("meat_results"),
        "team": get_df("team_results"),
        "anc_cat": get_df("ancillary_categories"),
        "anc": get_df("ancillary_results"),
        "anc_team": get_df("ancillary_team_results"),
    }


# ---------------------------------------------------
# DASHBOARD RENDER
# ---------------------------------------------------
def render():
    st.title("🔥 BBQ Results Dashboard")
    st.caption("Analyze results across competitions, meats, and ancillary categories")

    # Load DB
    tables = load_all()

    events = tables["events"]
    years = tables["years"]
    meats = tables["meats"]
    team = tables["team"]
    anc_cat = tables["anc_cat"]
    anc = tables["anc"]
    anc_team = tables["anc_team"]

    # -------------------------------------
    # BASIC VALIDATION
    # -------------------------------------
    if years.empty:
        st.warning("No competition years found.")
        st.stop()

    if events.empty:
        st.warning("No events found.")
        st.stop()

    # -------------------------------------
    # MERGE CORE MEATS
    # -------------------------------------
    if not meats.empty:
        core = (
            meats
            .merge(years, left_on="competition_year_id", right_on="id", suffixes=("", "_year"))
            .merge(events, left_on="event_id", right_on="id", suffixes=("", "_event"))
        )

        # Add team results
        if not team.empty:
            core = core.merge(
                team,
                left_on="competition_year_id",
                right_on="competition_year_id",
                how="left",
                suffixes=("", "_team"),
            )

        # Compute percentile rank
        core["Percentile Rank"] = 100 * (1 - ((core["rank"] - 1) / core["total_teams"]))
    else:
        core = pd.DataFrame()

    # -------------------------------------
    # MERGE ANCILLARY
    # -------------------------------------
    if not anc.empty:
        anc_df = (
            anc.merge(anc_cat, left_on="category_id", right_on="id", suffixes=("", "_cat"))
            .merge(years, left_on="competition_year_id", right_on="id", suffixes=("", "_year"))
            .merge(events, left_on="event_id", right_on="id", suffixes=("", "_event"))
        )

        if not anc_team.empty:
            anc_df = anc_df.merge(
                anc_team,
                left_on="competition_year_id",
                right_on="competition_year_id",
                how="left",
                suffixes=("", "_team")
            )

        anc_df["Percentile Rank"] = 100 * (1 - ((anc_df["rank"] - 1) / anc_df["total_teams"]))
    else:
        anc_df = pd.DataFrame()

    # -------------------------------------
    # UI TABS (Core Meats / Ancillary)
    # -------------------------------------
    tab1, tab2 = st.tabs(["🍖 Core Meats", "🍰 Ancillary Categories"])

    # ====================================================
    # ---------------- CORE MEATS TAB --------------------
    # ====================================================
    with tab1:
        st.subheader("🍖 Core Meat Results")

        if core.empty:
            st.info("No meat results available.")
        else:
            years_filter = sorted(core["year"].unique())
            events_filter = sorted(core["event_name"].unique())
            meats_filter = sorted(core["meat"].unique())

            c_year = st.selectbox("Year", ["All"] + [str(y) for y in years_filter])
            c_event = st.selectbox("Competition", ["All"] + events_filter)
            c_meats = st.multiselect("Meat", meats_filter, default=meats_filter)

            filtered = core.copy()
            if c_year != "All":
                filtered = filtered[filtered["year"].astype(str) == c_year]
            if c_event != "All":
                filtered = filtered[filtered["event_name"] == c_event]
            if c_meats:
                filtered = filtered[filtered["meat"].isin(c_meats)]

            st.dataframe(
                filtered[
                    [
                        "year",
                        "event_name",
                        "location",
                        "start_date",
                        "end_date",
                        "meat",
                        "participant",
                        "score",
                        "rank",
                        "Percentile Rank",
                        "total_score",
                        "rank_team",
                        "total_teams",
                    ]
                ],
                use_container_width=True,
            )

            # Trend line
            trend = (
                filtered.groupby(["year", "meat"], as_index=False)
                .agg({"Percentile Rank": "mean"})
            )

            if not trend.empty:
                fig = px.line(
                    trend,
                    x="year",
                    y="Percentile Rank",
                    color="meat",
                    markers=True,
                    title="Year-over-Year Percentile Trend (Core Meats)",
                )
                fig.update_yaxes(range=[0, 100])
                st.plotly_chart(fig, use_container_width=True)

    # ====================================================
    # ---------------- ANCILLARY TAB ---------------------
    # ====================================================
    with tab2:
        st.subheader("🍰 Ancillary Results")

        if anc_df.empty:
            st.info("No ancillary results available.")
        else:
            years_filter = sorted(anc_df["year"].unique())
            events_filter = sorted(anc_df["event_name"].unique())
            cats_filter = sorted(anc_df["category_name"].unique())

            a_year = st.selectbox("Year", ["All"] + [str(y) for y in years_filter], key="ayear")
            a_event = st.selectbox("Competition", ["All"] + events_filter, key="aevent")
            a_cat = st.multiselect("Category", cats_filter, default=cats_filter, key="acat")

            filtered = anc_df.copy()
            if a_year != "All":
                filtered = filtered[filtered["year"].astype(str) == a_year]
            if a_event != "All":
                filtered = filtered[filtered["event_name"] == a_event]
            if a_cat:
                filtered = filtered[filtered["category_name"].isin(a_cat)]

            st.dataframe(
                filtered[
                    [
                        "year",
                        "event_name",
                        "location",
                        "start_date",
                        "end_date",
                        "category_name",
                        "participant",
                        "score",
                        "rank",
                        "Percentile Rank",
                        "total_score",
                        "rank_team",
                        "total_teams",
                    ]
                ],
                use_container_width=True,
            )

            # Trend line
            trend = (
                filtered.groupby(["year", "category_name"], as_index=False)
                .agg({"Percentile Rank": "mean"})
            )

            if not trend.empty:
                fig = px.line(
                    trend,
                    x="year",
                    y="Percentile Rank",
                    color="category_name",
                    markers=True,
                    title="Year-over-Year Percentile Trend (Ancillary)",
                )
                fig.update_yaxes(range=[0, 100])
                st.plotly_chart(fig, use_container_width=True)
