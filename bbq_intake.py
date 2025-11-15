import streamlit as st
import pandas as pd
from datetime import date
import uuid
import requests
import os
from supabase_client import supabase_insert, supabase_get, supabase_upsert, supabase_delete
from utils import MEATS

# st.set_page_config(page_title="BBQ Competition Intake Form", layout="centered")
def render():
    st.title("🍴 Intake Form — Competitions & Results")
    # -------------------------
    # Helper: safe load table into DataFrame
    # -------------------------
    def load_table(table_name):
        resp = supabase_get(table_name)
        if resp.status_code == 200:
            data = resp.json()
            return pd.DataFrame(data) if data else pd.DataFrame()
        else:
            return pd.DataFrame()

    # -------------------------
    # Load master data
    # -------------------------
    events_df = load_table("competition_events")
    years_df = load_table("competition_years")
    meat_df_all = load_table("meat_results")
    anc_cat_all = load_table("ancillary_categories")
    anc_res_all = load_table("ancillary_results")
    team_results_all = load_table("team_results")
    anc_team_all = load_table("ancillary_team_results")

    # -------------------------
    # Event (stable) Create / Select
    # -------------------------
    st.subheader("1) Competition Event (stable)")
    event_options = ["-- New Event --"] + (events_df["event_name"].tolist() if not events_df.empty else [])
    selected_event = st.selectbox("Event (name)", event_options)

    if selected_event == "-- New Event --":
        new_event_name = st.text_input("Event Name")
        new_event_location = st.text_input("Location")
        if st.button("Create Event"):
            if not new_event_name or not new_event_location:
                st.error("Name and location required")
            else:
                resp = supabase_insert("competition_events", {"event_name": new_event_name.strip(), "location": new_event_location.strip()})
                if resp.status_code in (200, 201):
                    st.success("Event created")
                    st.experimental_rerun()
                else:
                    st.error(resp.text)
    else:
        ev_row = events_df[events_df["event_name"] == selected_event].iloc[0]
        st.markdown(f"**Selected:** {ev_row['event_name']} — {ev_row['location']}")

    # -------------------------
    # Competition Year (occurrence) Create / Select
    # -------------------------
    st.subheader("2) Competition Year / Occurrence")
    years_for_event = ["-- New Year --"]
    if not events_df.empty and selected_event != "-- New Event --":
        ev_id = events_df[events_df["event_name"] == selected_event]["id"].values[0]
        years_for_event += years_df[years_df["event_id"] == ev_id]["year"].astype(str).tolist()

    selected_year_option = st.selectbox("Select Year/Occurrence", years_for_event)

    if selected_year_option == "-- New Year --":
        occ_year = st.number_input("Year", min_value=2000, max_value=2100, value=date.today().year)
        start_date = st.date_input("Start Date")
        end_date = st.date_input("End Date", value=start_date)
        total_teams = st.number_input("Total Teams (optional)", min_value=0, value=0)
        if st.button("Create Competition Year"):
            if selected_event == "-- New Event --":
                st.error("Select or create an Event first")
            else:
                ev_id = events_df[events_df["event_name"] == selected_event]["id"].values[0]
                payload = {
                    "event_id": ev_id,
                    "year": int(occ_year),
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                }
                if total_teams > 0:
                    payload["total_teams"] = int(total_teams)
                resp = supabase_insert("competition_years", payload)
                if resp.status_code in (200,201):
                    st.success("Competition year created")
                    st.experimental_rerun()
                else:
                    st.error(resp.text)
    else:
        st.markdown(f"**Selected Year:** {selected_year_option}")

    # -------------------------
    # Determine selected competition_year_id
    # -------------------------
    competition_year_id = None
    if selected_year_option != "-- New Year --" and selected_event != "-- New Event --":
        ev_id = events_df[events_df["event_name"] == selected_event]["id"].values[0]
        matched = years_df[(years_df["event_id"] == ev_id) & (years_df["year"].astype(str) == selected_year_option)]
        if not matched.empty:
            competition_year_id = matched.iloc[0]["id"]

    # -------------------------
    # Load existing rows for the selected competition_year_id
    # -------------------------
    def df_filter_by_cy(df, cy_id):
        if df.empty or cy_id is None:
            return pd.DataFrame()
        if "competition_year_id" in df.columns:
            return df[df["competition_year_id"] == cy_id].copy()
        # backwards compat: if earlier schema used competition_id + year, try filtering
        return df

    meat_df = df_filter_by_cy(meat_df_all, competition_year_id)
    anc_cat_df = df_filter_by_cy(anc_cat_all, competition_year_id)
    anc_res_df = df_filter_by_cy(anc_res_all, competition_year_id)
    team_df = df_filter_by_cy(team_results_all, competition_year_id)
    anc_team_df = df_filter_by_cy(anc_team_all, competition_year_id)

    # -------------------------
    # 3) Core Meats section (inputs)
    # -------------------------
    st.subheader("3) Core Meats Results (KCBS)")
    core_inputs = {}

    for meat in MEATS:
        existing = meat_df[meat_df["meat"] == meat] if not meat_df.empty else pd.DataFrame()
        col1, col2, col3 = st.columns([4, 2, 2])

        with col1:
            participant = st.text_input(
                f"{meat} Participant",
                value=(existing["participant"].iloc[0] if not existing.empty else ""),
                key=f"{competition_year_id}_{meat}_participant",
            )
        with col2:
            score = st.number_input(
                f"{meat} Score",
                min_value=0.0,
                step=0.0001,
                format="%.4f",
                value=(float(existing["score"].iloc[0]) if not existing.empty and pd.notna(existing["score"].iloc[0]) else 0.0),
                key=f"{competition_year_id}_{meat}_score",
            )
        with col3:
            rank = st.number_input(
                f"{meat} Rank",
                min_value=0,
                step=1,
                value=(int(existing["rank"].iloc[0]) if not existing.empty and pd.notna(existing["rank"].iloc[0]) else 0),
                key=f"{competition_year_id}_{meat}_rank",
            )

        core_inputs[meat] = {"participant": participant or None, "score": float(score), "rank": int(rank)}

    # -------------------------
    # Core Team Totals (separated and displayed after core meats)
    # -------------------------
    st.subheader("4) Team Totals (Core Meats Only)")

    core_team_points = None
    core_team_rank = None
    if not team_df.empty:
        # expect one row per competition_year_id
        core_team_points = team_df["total_score"].iloc[0] if "total_score" in team_df.columns else None
        core_team_rank = team_df["rank"].iloc[0] if "rank" in team_df.columns else None

    colA, colB = st.columns(2)
    with colA:
        core_team_points = st.number_input(
            "Total Core Score",
            min_value=0.0,
            step=0.0001,
            format="%.4f",
            value=float(core_team_points) if core_team_points is not None else 0.0,
            key=f"{competition_year_id}_core_team_points",
        )
    with colB:
        core_team_rank = st.number_input(
            "Team Rank (Core Meats)",
            min_value=0,
            step=1,
            value=int(core_team_rank) if core_team_rank is not None else 0,
            key=f"{competition_year_id}_core_team_rank",
        )

    # -------------------------
    # 5) Ancillary Categories & Results (competition-year-specific)
    # -------------------------
    st.subheader("5) Ancillary / Sides / Misc Categories")

    # Build list of categories for this competition_year (allow adding new)
    existing_categories = anc_cat_df["category_name"].tolist() if not anc_cat_df.empty else []
    new_cat = st.text_input("Add a new ancillary category (optional)")
    if new_cat:
        if new_cat.strip() not in existing_categories:
            existing_categories.append(new_cat.strip())

    anc_inputs = {}
    for cat in existing_categories:
        # find existing result for this category if any (usually one per team)
        existing_row = pd.DataFrame()
        if not anc_res_df.empty and "category_id" in anc_res_df.columns:
            # we need category id mapping: find category id for this name in anc_cat_df
            if not anc_cat_df.empty and "category_name" in anc_cat_df.columns:
                cat_rows = anc_cat_df[anc_cat_df["category_name"] == cat]
                if not cat_rows.empty:
                    cat_id = cat_rows.iloc[0]["id"]
                    existing_row = anc_res_df[anc_res_df["category_id"] == cat_id]

        c1, c2, c3 = st.columns([4, 2, 2])
        with c1:
            participant = st.text_input(f"{cat} Participant", value=(existing_row["participant"].iloc[0] if not existing_row.empty else ""), key=f"{competition_year_id}_{cat}_participant")
        with c2:
            score = st.number_input(f"{cat} Score", min_value=0.0, step=0.0001, format="%.4f", value=(float(existing_row["score"].iloc[0]) if not existing_row.empty and pd.notna(existing_row["score"].iloc[0]) else 0.0), key=f"{competition_year_id}_{cat}_score")
        with c3:
            rank = st.number_input(f"{cat} Rank", min_value=0, step=1, value=(int(existing_row["rank"].iloc[0]) if not existing_row.empty and pd.notna(existing_row["rank"].iloc[0]) else 0), key=f"{competition_year_id}_{cat}_rank")
        anc_inputs[cat] = {"participant": participant or None, "score": float(score), "rank": int(rank)}

    # -------------------------
    # Ancillary Team Totals (separated and displayed after ancillary)
    # -------------------------
    st.subheader("6) Team Totals (Ancillary Only)")

    anc_team_points = None
    anc_team_rank = None
    if not anc_team_df.empty:
        anc_team_points = anc_team_df["total_score"].iloc[0] if "total_score" in anc_team_df.columns else None
        anc_team_rank = anc_team_df["rank"].iloc[0] if "rank" in anc_team_df.columns else None

    cA, cB = st.columns(2)
    with cA:
        anc_team_points = st.number_input(
            "Total Ancillary Score",
            min_value=0.0,
            step=0.0001,
            format="%.4f",
            value=float(anc_team_points) if anc_team_points is not None else 0.0,
            key=f"{competition_year_id}_anc_team_points",
        )
    with cB:
        anc_team_rank = st.number_input(
            "Team Rank (Ancillaries)",
            min_value=0,
            step=1,
            value=int(anc_team_rank) if anc_team_rank is not None else 0,
            key=f"{competition_year_id}_anc_team_rank",
        )

    # -------------------------
    # 7) SAVE / UPSERT logic
    # -------------------------
    if st.button("💾 Save All"):
        if not competition_year_id:
            st.error("Select or create a competition year first.")
            st.stop()

        # 7a: Upsert core meats (use on_conflict on competition_year_id,meat)
        for meat, vals in core_inputs.items():
            payload = {
                "competition_year_id": competition_year_id,
                "meat": meat,
                "participant": vals["participant"],
                "score": vals["score"],
                "rank": vals["rank"],
            }
            # upsert on competition_year_id + meat (unique logical key)
            resp = supabase_upsert("meat_results", payload, on_conflict="competition_year_id,meat")
            if resp.status_code not in (200,201):
                st.error(f"Error upserting meat {meat}: {resp.text}")

        # 7b: Upsert core team totals (unique competition_year_id)
        core_payload = {
            "competition_year_id": competition_year_id,
            "total_score": float(core_team_points),
            "rank": int(core_team_rank)
        }
        resp_core_team = supabase_upsert("team_results", core_payload, on_conflict="competition_year_id")
        if resp_core_team.status_code not in (200,201):
            st.error(f"Error saving core team totals: {resp_core_team.text}")

        # 7c: Ensure ancillary categories exist, then upsert ancillary results
        # first refresh ancillary categories for this competition_year
        anc_cat_df = load_table("ancillary_categories")
        anc_cat_df = anc_cat_df[anc_cat_df["competition_year_id"] == competition_year_id] if not anc_cat_df.empty else pd.DataFrame()

        for cat_name, vals in anc_inputs.items():
            # find category id
            cat_row = anc_cat_df[anc_cat_df["category_name"] == cat_name] if not anc_cat_df.empty else pd.DataFrame()
            if cat_row.empty:
                # create category
                r = supabase_insert("ancillary_categories", {"competition_year_id": competition_year_id, "category_name": cat_name})
                if r.status_code in (200,201):
                    cat_id = r.json()[0]["id"]
                    # update local anc_cat_df
                    anc_cat_df = pd.concat([anc_cat_df, pd.DataFrame([{"id": cat_id, "competition_year_id": competition_year_id, "category_name": cat_name}])], ignore_index=True)
                else:
                    st.error(f"Failed to create ancillary category {cat_name}: {r.text}")
                    continue
            else:
                cat_id = cat_row.iloc[0]["id"]

            payload = {
                "competition_year_id": competition_year_id,
                "category_id": cat_id,
                "participant": vals["participant"],
                "score": vals["score"],
                "rank": vals["rank"]
            }
            # upsert on competition_year_id + category_id (assumes one row per category per team)
            resp = supabase_upsert("ancillary_results", payload, on_conflict="competition_year_id,category_id")
            if resp.status_code not in (200,201):
                st.error(f"Error saving ancillary {cat_name}: {resp.text}")

        # 7d: Upsert ancillary team totals
        anc_team_payload = {
            "competition_year_id": competition_year_id,
            "total_score": float(anc_team_points),
            "rank": int(anc_team_rank)
        }
        resp_anc_team = supabase_upsert("ancillary_team_results", anc_team_payload, on_conflict="competition_year_id")
        if resp_anc_team.status_code not in (200,201):
            st.error(f"Error saving ancillary team totals: {resp_anc_team.text}")

        st.success("Saved all entries.")
        st.rerun()
    # # -----------------------------
    # # Load Competitions
    # # -----------------------------
    # comp_resp = supabase.table("competitions").select("*").order("competition_name").execute()
    # comp_df = pd.DataFrame(comp_resp.data or [])
    #
    # if comp_df.empty:
    #     st.error("No competitions found. Add competitions first.")
    #     st.stop()
    #
    # competition = st.selectbox("Competition", comp_df["competition_name"].tolist())
    # comp_id = int(comp_df.loc[comp_df["competition_name"] == competition, "id"].iloc[0])
    #
    # # -----------------------------
    # # Load Years for this Competition
    # # -----------------------------
    # year_resp = (
    #     supabase.table("competition_years")
    #     .select("year")
    #     .eq("competition_id", comp_id)
    #     .order("year", desc=True)
    #     .execute()
    # )
    #
    # year_df = pd.DataFrame(year_resp.data or [])
    #
    # year = st.selectbox("Year", year_df["year"].tolist() if not year_df.empty else [])
    #
    # # -----------------------------
    # # Load DB Data
    # # -----------------------------
    # # Core meats
    # core_resp = (
    #     supabase.table("results")
    #     .select("*")
    #     .eq("competition_id", comp_id)
    #     .eq("year", year)
    #     .execute()
    # )
    # core_df = pd.DataFrame(core_resp.data or [])
    #
    # # Competition year metadata (core team totals)
    # meta_resp = (
    #     supabase.table("competition_years")
    #     .select("*")
    #     .eq("competition_id", comp_id)
    #     .eq("year", year)
    #     .execute()
    # )
    # meta_df = pd.DataFrame(meta_resp.data or [])
    #
    # # Ancillary results
    # anc_resp = (
    #     supabase.table("ancillary_results")
    #     .select("*, categories(category_name)")
    #     .eq("competition_id", comp_id)
    #     .eq("year", year)
    #     .execute()
    # )
    # anc_df = pd.DataFrame(anc_resp.data or [])
    #
    # # Category list
    # cat_resp = supabase.table("categories").select("*").execute()
    # cat_df = pd.DataFrame(cat_resp.data or [])
    # cat_list = sorted(cat_df["category_name"].dropna().unique().tolist()) if not cat_df.empty else []
    #
    #
    # # =========================================================
    # #  🔥 SECTION 1: CORE MEAT RESULTS
    # # =========================================================
    # st.subheader("🍖 Core Meats Results (KCBS)")
    #
    # core_inputs = {}
    #
    # for meat in MEATS:
    #     existing = core_df[core_df["meat"] == meat]
    #
    #     col1, col2, col3 = st.columns([4, 2, 2])
    #
    #     with col1:
    #         p = st.text_input(
    #             f"{meat} Participant",
    #             value=existing["participant"].iloc[0] if not existing.empty else "",
    #             key=f"{comp_id}_{year}_{meat}_p",
    #         )
    #
    #     with col2:
    #         s = st.number_input(
    #             f"{meat} Score",
    #             min_value=0.0,
    #             step=0.0001,
    #             format="%.4f",
    #             value=float(existing["score"].iloc[0]) if not existing.empty else 0.0,
    #             key=f"{comp_id}_{year}_{meat}_s",
    #         )
    #
    #     with col3:
    #         r = st.number_input(
    #             f"{meat} Rank",
    #             min_value=0,
    #             step=1,
    #             value=int(existing["rank"].iloc[0]) if not existing.empty else 0,
    #             key=f"{comp_id}_{year}_{meat}_r",
    #         )
    #
    #     core_inputs[meat] = dict(participant=p, score=s, rank=r)
    #
    # # -----------------------------
    # # Core Team Totals (SEPARATED)
    # # -----------------------------
    # st.subheader("📊 Team Totals (Core Meats Only)")
    #
    # core_team_rank = int(meta_df["team_rank_core"].iloc[0]) if "team_rank_core" in meta_df else 0
    # core_team_points = float(meta_df["team_points_core"].iloc[0]) if "team_points_core" in meta_df else 0.0
    #
    # colA, colB = st.columns(2)
    # with colA:
    #     core_team_points = st.number_input(
    #         "Total Core Score",
    #         min_value=0.0,
    #         step=0.0001,
    #         format="%.4f",
    #         value=core_team_points,
    #         key=f"{comp_id}_{year}_core_team_points",
    #     )
    # with colB:
    #     core_team_rank = st.number_input(
    #         "Team Rank (Core Meats)",
    #         min_value=0,
    #         step=1,
    #         value=core_team_rank,
    #         key=f"{comp_id}_{year}_core_team_rank",
    #     )
    #
    # # =========================================================
    # #  🔥 SECTION 2: ANCILLARY RESULTS
    # # =========================================================
    # st.subheader("🍽️ Ancillary Categories")
    #
    # anc_inputs = {}
    #
    # for _, row in cat_df.iterrows():
    #     category_id = row["id"]
    #     category_name = row["category_name"]
    #
    #     cat_rec = anc_df[anc_df["category_id"] == category_id]
    #
    #     col1, col2, col3 = st.columns([4, 2, 2])
    #
    #     with col1:
    #         p = st.text_input(
    #             f"{category_name} Participant",
    #             value=cat_rec["participant"].iloc[0] if not cat_rec.empty else "",
    #             key=f"{comp_id}_{year}_{category_name}_p",
    #         )
    #
    #     with col2:
    #         s = st.number_input(
    #             f"{category_name} Score",
    #             min_value=0.0,
    #             step=0.0001,
    #             format="%.4f",
    #             value=float(cat_rec["score"].iloc[0]) if not cat_rec.empty else 0.0,
    #             key=f"{comp_id}_{year}_{category_name}_s",
    #         )
    #
    #     with col3:
    #         r = st.number_input(
    #             f"{category_name} Rank",
    #             min_value=0,
    #             step=1,
    #             value=int(cat_rec["rank"].iloc[0]) if not cat_rec.empty else 0,
    #             key=f"{comp_id}_{year}_{category_name}_r",
    #         )
    #
    #     anc_inputs[category_id] = dict(
    #         participant=p,
    #         score=s,
    #         rank=r,
    #     )
    #
    # # -----------------------------
    # # Ancillary Team Totals (SEPARATED)
    # # -----------------------------
    # st.subheader("📊 Team Totals (Ancillary Only)")
    #
    # anc_team_rank = int(meta_df["team_rank_anc"].iloc[0]) if "team_rank_anc" in meta_df else 0
    # anc_team_points = float(meta_df["team_points_anc"].iloc[0]) if "team_points_anc" in meta_df else 0.0
    #
    # colA, colB = st.columns(2)
    # with colA:
    #     anc_team_points = st.number_input(
    #         "Total Ancillary Score",
    #         min_value=0.0,
    #         step=0.0001,
    #         format="%.4f",
    #         value=anc_team_points,
    #         key=f"{comp_id}_{year}_anc_team_points",
    #     )
    # with colB:
    #     anc_team_rank = st.number_input(
    #         "Team Rank (Ancillaries)",
    #         min_value=0,
    #         step=1,
    #         value=anc_team_rank,
    #         key=f"{comp_id}_{year}_anc_team_rank",
    #     )
    #
    #
    # # =========================================================
    # #  🔥 SAVE BUTTON
    # # =========================================================
    # if st.button("💾 Save All Data"):
    #     # Save core meats
    #     for meat, info in core_inputs.items():
    #         existing = core_df[core_df["meat"] == meat]
    #         payload = {
    #             "competition_id": comp_id,
    #             "year": year,
    #             "meat": meat,
    #             "participant": info["participant"],
    #             "score": info["score"],
    #             "rank": info["rank"],
    #         }
    #         if not existing.empty:
    #             supabase.table("results").update(payload).eq("id", existing["id"].iloc[0]).execute()
    #         else:
    #             supabase.table("results").insert(payload).execute()
    #
    #     # Save core team totals
    #     supabase.table("competition_years").update({
    #         "team_points_core": core_team_points,
    #         "team_rank_core": core_team_rank,
    #         "team_points_anc": anc_team_points,
    #         "team_rank_anc": anc_team_rank,
    #     }).eq("competition_id", comp_id).eq("year", year).execute()
    #
    #     # Save ancillary
    #     for category_id, info in anc_inputs.items():
    #         existing = anc_df[anc_df["category_id"] == category_id]
    #         payload = {
    #             "competition_id": comp_id,
    #             "year": year,
    #             "category_id": category_id,
    #             "participant": info["participant"],
    #             "score": info["score"],
    #             "rank": info["rank"],
    #         }
    #         if not existing.empty:
    #             supabase.table("ancillary_results").update(payload).eq("id", existing["id"].iloc[0]).execute()
    #         else:
    #             supabase.table("ancillary_results").insert(payload).execute()
    #
    #     st.success("Saved Successfully!")

    # # Sidebar info
    # st.sidebar.info("Enter competition results here. Data will be stored in the database.")
    #
    # # Load events and competition years
    # @st.cache_data
    # def load_events_and_years():
    #     ev_resp = supabase_get("competition_events")
    #     events = pd.DataFrame(ev_resp.json()) if ev_resp.status_code == 200 else pd.DataFrame()
    #     cy_resp = supabase_get("competition_years")
    #     years = pd.DataFrame(cy_resp.json()) if cy_resp.status_code == 200 else pd.DataFrame()
    #     return events, years
    #
    # events_df, years_df = load_events_and_years()
    #
    # # Event selection / create
    # st.subheader("Competition Event (stable)")
    # event_options = ["-- New Event --"] + (events_df["event_name"].tolist() if not events_df.empty else [])
    # selected_event = st.selectbox("Event (name)", event_options)
    #
    # if selected_event == "-- New Event --":
    #     new_event_name = st.text_input("Event Name")
    #     new_event_location = st.text_input("Location")
    #     if st.button("Create Event"):
    #         if not new_event_name or not new_event_location:
    #             st.error("Name and location required")
    #         else:
    #             resp = supabase_insert("competition_events", {"event_name": new_event_name, "location": new_event_location})
    #             if resp.status_code in (200,201):
    #                 st.success("Event created")
    #                 st.experimental_rerun()
    #             else:
    #                 st.error(resp.text)
    # else:
    #     ev_row = events_df[events_df["event_name"] == selected_event].iloc[0]
    #     st.markdown(f"**Selected:** {ev_row['event_name']} — {ev_row['location']}")
    #
    # # Competition Year (occurrence) create / select
    # st.subheader("Competition Year / Occurrence")
    # years_for_event = ["-- New Year --"]
    # if not years_df.empty and selected_event != "-- New Event --":
    #     ev_id = events_df[events_df["event_name"] == selected_event]["id"].values[0]
    #     years_for_event += years_df[years_df["event_id"] == ev_id]["year"].astype(str).tolist()
    #
    # selected_year_option = st.selectbox("Select Year/Occurrence", years_for_event)
    #
    # if selected_year_option == "-- New Year --":
    #     occ_year = st.number_input("Year", min_value=2000, max_value=2100, value=date.today().year)
    #     start_date = st.date_input("Start Date")
    #     end_date = st.date_input("End Date", value=start_date)
    #     total_teams = st.number_input("Total Teams (optional)", min_value=0, value=0)
    #     if st.button("Create Competition Year"):
    #         if selected_event == "-- New Event --":
    #             st.error("Select or create an Event first")
    #         else:
    #             ev_id = events_df[events_df["event_name"] == selected_event]["id"].values[0]
    #             payload = {
    #                 "event_id": ev_id,
    #                 "year": int(occ_year),
    #                 "start_date": start_date.isoformat(),
    #                 "end_date": end_date.isoformat(),
    #                 "total_teams": int(total_teams) if total_teams > 0 else None
    #             }
    #             resp = supabase_insert("competition_years", payload)
    #             if resp.status_code in (200,201):
    #                 st.success("Competition year created")
    #                 st.experimental_rerun()
    #             else:
    #                 st.error(resp.text)
    # else:
    #     st.markdown(f"**Selected Year:** {selected_year_option}")
    #
    # # Once competition_year is selected, allow adding results
    # st.subheader("Add Results for Selected Competition Year")
    # if selected_event == "-- New Event --" and selected_year_option == "-- New Year --":
    #     st.info("Create/select event and year first.")
    #     st.stop()
    #
    # # determine competition_year_id
    # competition_year_id = None
    # if selected_year_option != "-- New Year --":
    #     ev_id = events_df[events_df["event_name"] == selected_event]["id"].values[0]
    #     comp_row = years_df[(years_df["event_id"] == ev_id) & (years_df["year"].astype(str) == selected_year_option)]
    #     if not comp_row.empty:
    #         competition_year_id = comp_row.iloc[0]["id"]
    #
    # # Core meat results form
    # st.markdown("### Core meats")
    # with st.form("core_meats"):
    #     cols = st.columns((2,1,1))
    #     rows = []
    #     for meat in MEATS:
    #         participant = cols[0].text_input(f"{meat} Participant", key=f"{meat}_p")
    #         score = cols[1].number_input(f"{meat} Score", min_value=0.0, step=0.001, key=f"{meat}_s")
    #         rank = cols[2].number_input(f"{meat} Rank", min_value=1, step=1, key=f"{meat}_r")
    #         rows.append({"meat": meat, "participant": participant, "score": score, "rank": rank})
    #     submitted = st.form_submit_button("Save Core Meat Results")
    #     if submitted:
    #         if not competition_year_id:
    #             st.error("Select competition year first")
    #         else:
    #             for r in rows:
    #                 payload = {
    #                     "competition_year_id": competition_year_id,
    #                     "meat": r["meat"],
    #                     "participant": r["participant"] or None,
    #                     "score": float(r["score"]) if r["score"] else None,
    #                     "rank": int(r["rank"]) if r["rank"] else None
    #                 }
    #                 resp = supabase_insert("meat_results", payload)
    #                 if resp.status_code not in (200,201):
    #                     st.error(resp.text)
    #             st.success("Core meat results saved!")
    #
    # # Team totals - Core Meats
    # st.markdown("### Team Totals - Core Meats")
    # with st.form("team_totals_core_meats"):
    #     core_total = st.number_input("Core Meats Total Score", min_value=0.0, step=0.001)
    #     core_rank = st.number_input("Core Team Rank", min_value=1, step=1)
    #     submit_tot = st.form_submit_button("Save Meat Totals")
    #     if submit_tot:
    #         if not competition_year_id:
    #             st.error("Select competition year first")
    #         else:
    #             r1 = supabase_insert("team_results", {"competition_year_id": competition_year_id, "total_score": float(core_total), "rank": int(core_rank)})
    #             if r1.status_code not in (200,201):
    #                 st.error(r1.text)
    #             st.success("Meat totals saved!")
    #
    # # Ancillary categories
    # st.markdown("### Ancillary / Sides")
    # with st.form("ancillary"):
    #     new_category = st.text_input("Add a new ancillary category (e.g., Sausage, Veggies)")
    #     cat_list = []
    #     if competition_year_id:
    #         resp = supabase_get("ancillary_categories", params=f"competition_year_id=eq.{competition_year_id}")
    #         if resp.status_code == 200:
    #             cat_df = pd.DataFrame(resp.json())
    #             if "category_name" in cat_df.columns:
    #                 cat_list = cat_df["category_name"].tolist()
    #     if new_category:
    #         cat_list.append(new_category.strip())
    #     ancillary_entries = []
    #     for cat in cat_list:
    #         st.markdown(f"**{cat}**")
    #         p = st.text_input(f"{cat} Participant", key=f"{cat}_p")
    #         s = st.number_input(f"{cat} Score", min_value=0.0, step=0.0001, format="%.4f", key=f"{cat}_s")
    #         rnk = st.number_input(f"{cat} Rank", min_value=1, step=1, key=f"{cat}_r")
    #         ancillary_entries.append({"category_name": cat, "participant": p, "score": s, "rank": rnk})
    #     submit_anc = st.form_submit_button("Save Ancillary Results")
    #     if submit_anc:
    #         if not competition_year_id:
    #             st.error("Select competition year first")
    #         else:
    #             # ensure categories exist and insert results
    #             for e in ancillary_entries:
    #                 # create category if missing
    #                 params = f"competition_year_id=eq.{competition_year_id}&category_name=eq.{e['category_name']}"
    #                 resp = supabase_get("ancillary_categories", params=params)
    #                 if resp.status_code == 200 and resp.json():
    #                     cat_id = resp.json()[0]["id"]
    #                 else:
    #                     r = supabase_insert("ancillary_categories", {"competition_year_id": competition_year_id, "category_name": e["category_name"]})
    #                     if r.status_code in (200,201):
    #                         cat_id = r.json()[0]["id"]
    #                     else:
    #                         st.error(r.text); continue
    #                 payload = {
    #                     "competition_year_id": competition_year_id,
    #                     "category_id": cat_id,
    #                     "participant": e["participant"] or None,
    #                     "score": float(e["score"]) if e["score"] else None,
    #                     "rank": int(e["rank"]) if e["rank"] else None
    #                 }
    #                 rr = supabase_insert("ancillary_results", payload)
    #                 if rr.status_code not in (200,201):
    #                     st.error(rr.text)
    #             st.success("Ancillary results saved!")
    #
    # # Team totals - Core Meats
    # st.markdown("### Team Totals - Ancillary")
    # with st.form("team_totals_ancillary"):
    #     anc_total = st.number_input("Ancillary Total Score", min_value=0.0, step=0.001)
    #     anc_rank = st.number_input("Ancillary Team Rank", min_value=1, step=1)
    #     submit_tot = st.form_submit_button("Save Ancillary Totals")
    #     if submit_tot:
    #         if not competition_year_id:
    #             st.error("Select competition year first")
    #         else:
    #             r2 = supabase_insert("ancillary_team_results", {"competition_year_id": competition_year_id, "total_score": float(anc_total), "rank": int(anc_rank)})
    #             if r2.status_code not in (200,201):
    #                 st.error(r2.text)
    #             st.success("Ancillary totals saved!")
