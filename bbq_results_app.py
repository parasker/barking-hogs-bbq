#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 10 13:21:16 2025

@author: sudheerparasker
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="BBQ Team Results Tracker", layout="wide")

st.title("🔥 BBQ Team Results Tracker")
st.caption("Analyze KCBS competition results — meats, participants, and year-over-year performance")

# --- CONFIG ---
DEFAULT_FILE = "Barking Hogs BBQ.xlsx"

# --- Function to Load Excel Data ---
@st.cache_data
def load_data(file_path):
    xls = pd.ExcelFile(file_path)
    all_data = []

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        expected_cols = {"Year", "Meat", "Participant", "Score", "Rank", "Location"}
        if expected_cols.issubset(df.columns):
            df["Sheet"] = sheet
            all_data.append(df)

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    else:
        return pd.DataFrame(columns=["Year", "Meat", "Participant", "Score", "Rank", "Location", "Sheet"])

# --- Load Excel Automatically if Exists ---
if os.path.exists(DEFAULT_FILE):
    st.sidebar.success(f"✅ Found local file: {DEFAULT_FILE}")
    data = load_data(DEFAULT_FILE)
else:
    st.sidebar.warning(f"⚠️ No local file named '{DEFAULT_FILE}' found.")
    uploaded_file = st.sidebar.file_uploader("Upload BBQ Results Excel (.xlsx)", type=["xlsx"])
    if uploaded_file:
        data = load_data(uploaded_file)
    else:
        st.info("No data available. Please upload your Excel file to continue.")
        st.stop()

# --- Filters ---
st.sidebar.header("🔍 Filters")
years = sorted(data["Year"].dropna().unique())
locations = sorted(data["Location"].dropna().unique())

selected_year = st.sidebar.selectbox("Select Year", ["All"] + [str(y) for y in years])
selected_location = st.sidebar.selectbox("Select Location", ["All"] + locations)

filtered = data.copy()
if selected_year != "All":
    filtered = filtered[filtered["Year"].astype(str) == selected_year]
if selected_location != "All":
    filtered = filtered[filtered["Location"] == selected_location]

# --- Overview ---
st.subheader("🏁 Competition Results Summary")
st.dataframe(filtered, use_container_width=True)

# --- Metrics ---
if not filtered.empty:
    avg_score = filtered["Score"].mean()
    best_meat = filtered.loc[filtered["Score"].idxmax()]
    avg_rank = filtered["Rank"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("Average Score", f"{avg_score:.2f}")
    col2.metric("Average Rank", f"{avg_rank:.1f}")
    col3.metric("Top Category", f"{best_meat['Meat']} ({best_meat['Score']:.2f})")

# --- Visualization ---
st.subheader("🍖 Meat Category Performance")
fig = px.bar(
    filtered,
    x="Meat",
    y="Score",
    color="Participant",
    text="Rank",
    title="Scores by Meat Category",
    hover_data=["Year", "Location"],
    labels={"Score": "KCBS Score", "Meat": "Category"}
)
st.plotly_chart(fig, use_container_width=True)

# --- Yearly Trend ---
st.subheader("📈 Year-over-Year Trend")
trend = (
    data.groupby(["Year", "Meat"], as_index=False)
    .agg({"Score": "mean"})
    .sort_values("Year")
)
if not trend.empty:
    fig_trend = px.line(
        trend,
        x="Year",
        y="Score",
        color="Meat",
        markers=True,
        title="Average Score Trend by Year"
    )
    st.plotly_chart(fig_trend, use_container_width=True)

# --- Rank Distribution ---
st.subheader("🏆 Rank Distribution")
fig_rank = px.box(
    filtered,
    x="Meat",
    y="Rank",
    color="Meat",
    title="Rank Spread per Category",
    points="all"
)
st.plotly_chart(fig_rank, use_container_width=True)

# --- Footer ---
st.markdown("---")
st.caption("✅ Future Features: multi-year comparisons • participant stats • PDF reports • predictive analysis")
