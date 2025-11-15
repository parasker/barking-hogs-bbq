# migration_tool.py
import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from supabase_client import supabase_get, supabase_insert, supabase_upsert
from utils import sidebar_logo, app_navigation

def render():
    st.title("📥 Migration Tool — Upload, Validate, Import")

    uploaded = st.file_uploader("Upload Excel or CSV (legacy export)", type=["xlsx", "xls", "csv"])
    if not uploaded:
        st.info("Upload a file to begin.")
        st.stop()

    # Read file
    try:
        if uploaded.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            xls = pd.ExcelFile(uploaded)
            # concat all sheets
            frames = [pd.read_excel(xls, sheet_name=sh) for sh in xls.sheet_names]
            df = pd.concat(frames, ignore_index=True, sort=False)
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        st.stop()

    st.write("Preview (first 200 rows):")
    st.dataframe(df.head(200))

    # normalize column names
    df.columns = [c.strip() for c in df.columns]

    # REQUIRED FIELDS (best-effort mapping)
    # flexible column mapping
    col_map = {
        "year": None,
        "event": None,
        "location": None,
        "competition_dates": None,
        "start_date": None,
        "end_date": None,
        "meat": None,
        "participant": None,
        "score": None,
        "rank": None,
        "total_teams": None,
        "team_total_score": None,
        "team_rank": None,
        "ancillary_category": None,
        "ancillary_total_score": None,
        "ancillary_team_rank": None
    }

    # auto-detect common names
    for c in df.columns:
        lc = c.lower()
        if "year" == lc or lc.startswith("year"):
            col_map["year"] = c
        if lc in ("competition","competition name","event","event name","location"):
            col_map["event"] = c
        if lc in ("location","venue"):
            col_map["location"] = c
        if lc in ("competition dates","competition_date","dates","date range"):
            col_map["competition_dates"] = c
        if lc in ("start_date","start date","start"):
            col_map["start_date"] = c
        if lc in ("end_date","end date","end"):
            col_map["end_date"] = c
        if lc in ("meat","category","submission"):
            col_map["meat"] = c
        if lc in ("participant","member","cook"):
            col_map["participant"] = c
        if lc in ("score","scores"):
            col_map["score"] = c
        if lc in ("rank","placement"):
            col_map["rank"] = c
        if lc in ("total teams","total_teams","teams"):
            col_map["total_teams"] = c
        if lc in ("team total","team_total","team score","team_score"):
            col_map["team_total_score"] = c
        if lc in ("team rank","team_rank"):
            col_map["team_rank"] = c
        if lc in ("category","ancillary","ancillary category","side"):
            col_map["ancillary_category"] = c
        if lc in ("ancillary_total","sides total","side total"):
            col_map["ancillary_total_score"] = c
        if lc in ("ancillary team rank","sides rank","ancillary_team_rank"):
            col_map["ancillary_team_rank"] = c

    st.subheader("Detected column mapping")
    st.json(col_map)

    # validation rules
    errors = []
    rows_to_import = []

    def parse_date_range(text):
        if pd.isna(text) or not text:
            return None, None
        s = str(text).strip()
        if "to" in s:
            parts = [p.strip() for p in s.split("to")]
            try:
                return pd.to_datetime(parts[0]).date(), pd.to_datetime(parts[1]).date()
            except:
                return None, None
        else:
            try:
                d = pd.to_datetime(s).date()
                return d, d
            except:
                return None, None

    for idx, row in df.iterrows():
        row_errors = []
        year = row.get(col_map["year"]) if col_map["year"] in row.index else None
        event = row.get(col_map["event"]) if col_map["event"] in row.index else None
        location = row.get(col_map["location"]) if col_map["location"] in row.index else None
        comp_dates = row.get(col_map["competition_dates"]) if col_map["competition_dates"] in row.index else None
        start_d = row.get(col_map["start_date"]) if col_map["start_date"] in row.index else None
        end_d = row.get(col_map["end_date"]) if col_map["end_date"] in row.index else None

        # event name required
        if pd.isna(event) or str(event).strip() == "" or str(event).strip().lower() == "nan":
            row_errors.append("Missing event/competition name")
        # year required
        if pd.isna(year):
            row_errors.append("Missing year")
        # location required
        if pd.isna(location) or str(location).strip() == "" or str(location).strip().lower() == "nan":
            row_errors.append("Missing location")
        # parse dates
        sd, ed = None, None
        if comp_dates and not pd.isna(comp_dates):
            sd, ed = parse_date_range(comp_dates)
        else:
            if start_d and not pd.isna(start_d):
                try:
                    sd = pd.to_datetime(start_d).date()
                except:
                    row_errors.append("Invalid start date")
            if end_d and not pd.isna(end_d):
                try:
                    ed = pd.to_datetime(end_d).date()
                except:
                    row_errors.append("Invalid end date")
        # total teams optional but if present must be integer
        tt = None
        if col_map["total_teams"] and col_map["total_teams"] in row.index:
            val = row.get(col_map["total_teams"])
            if not pd.isna(val):
                try:
                    tt = int(val)
                except:
                    row_errors.append("Invalid total_teams")

        # meat/ancillary detection and score/rank validation
        meat = row.get(col_map["meat"]) if col_map["meat"] in row.index else None
        ancillary = row.get(col_map["ancillary_category"]) if col_map["ancillary_category"] in row.index else None
        score = row.get(col_map["score"]) if col_map["score"] in row.index else None
        rank = row.get(col_map["rank"]) if col_map["rank"] in row.index else None

        # If meat/ancillary present then score & rank should be numeric
        if (not pd.isna(meat) and str(meat).strip() != "") or (not pd.isna(ancillary) and str(ancillary).strip() != ""):
            if pd.isna(score):
                row_errors.append("Missing score")
            if pd.isna(rank):
                row_errors.append("Missing rank")

        if row_errors:
            errors.append({"row": int(idx)+2, "errors": row_errors})
        else:
            rows_to_import.append({
                "year": int(year) if not pd.isna(year) else None,
                "event": str(event).strip(),
                "location": str(location).strip(),
                "start_date": sd,
                "end_date": ed,
                "total_teams": tt,
                "meat": None if pd.isna(meat) else str(meat).strip(),
                "ancillary_category": None if pd.isna(ancillary) else str(ancillary).strip(),
                "participant": None if pd.isna(row.get(col_map["participant"])) else str(row.get(col_map["participant"])).strip(),
                "score": None if pd.isna(score) else float(score),
                "rank": None if pd.isna(rank) else int(rank),
                "team_total_score": None if col_map["team_total_score"] not in row.index or pd.isna(row.get(col_map["team_total_score"])) else float(row.get(col_map["team_total_score"])),
                "team_rank": None if col_map["team_rank"] not in row.index or pd.isna(row.get(col_map["team_rank"])) else int(row.get(col_map["team_rank"])),
                "ancillary_team_total": None if col_map["ancillary_total_score"] not in row.index or pd.isna(row.get(col_map["ancillary_total_score"])) else float(row.get(col_map["ancillary_total_score"])),
                "ancillary_team_rank": None if col_map["ancillary_team_rank"] not in row.index or pd.isna(row.get(col_map["ancillary_team_rank"])) else int(row.get(col_map["ancillary_team_rank"]))
            })

    st.subheader("Validation Results")
    if errors:
        st.error(f"Found {len(errors)} validation errors. Fix the file and try again.")
        st.json(errors)
        st.stop()
    else:
        st.success(f"Validation passed for {len(rows_to_import)} rows. Ready to import.")

    # Confirm import
    if st.button("Import into Supabase"):
        st.info("Starting import. This may take a few moments...")
        # caches
        event_cache = {}
        year_cache = {}
        ancillary_cache = {}

        def get_or_create_event(name, location):
            key = (name.lower(), location.lower())
            if key in event_cache:
                return event_cache[key]
            # try find
            resp = supabase_get("competition_events", params=f"event_name=eq.{quote_param(name)}&location=eq.{quote_param(location)}")
            if resp.status_code == 200 and resp.json():
                eid = resp.json()[0]["id"]
                event_cache[key] = eid
                return eid
            # create
            payload = {"event_name": name, "location": location}
            r = supabase_insert("competition_events", payload)
            r.raise_for_status()
            eid = r.json()[0]["id"]
            event_cache[key] = eid
            return eid

        def get_or_create_competition_year(event_id, year, start_date, end_date, total_teams):
            key = (event_id, int(year))
            if key in year_cache:
                return year_cache[key]
            # try find
            params = f"event_id=eq.{event_id}&year=eq.{year}"
            resp = supabase_get("competition_years", params=params)
            if resp.status_code == 200 and resp.json():
                cyid = resp.json()[0]["id"]
                year_cache[key] = cyid
                return cyid
            payload = {"event_id": event_id, "year": int(year)}
            if start_date:
                payload["start_date"] = start_date.isoformat()
            if end_date:
                payload["end_date"] = end_date.isoformat()
            if total_teams is not None:
                payload["total_teams"] = total_teams
            r = supabase_insert("competition_years", payload)
            r.raise_for_status()
            cyid = r.json()[0]["id"]
            year_cache[key] = cyid
            return cyid

        def get_or_create_ancillary_category(comp_year_id, cat_name):
            key = (comp_year_id, cat_name.lower())
            if key in ancillary_cache:
                return ancillary_cache[key]
            params = f"competition_year_id=eq.{comp_year_id}&category_name=eq.{quote_param(cat_name)}"
            resp = supabase_get("ancillary_categories", params=params)
            if resp.status_code == 200 and resp.json():
                cid = resp.json()[0]["id"]
                ancillary_cache[key] = cid
                return cid
            payload = {"competition_year_id": comp_year_id, "category_name": cat_name}
            r = supabase_insert("ancillary_categories", payload)
            r.raise_for_status()
            cid = r.json()[0]["id"]
            ancillary_cache[key] = cid
            return cid

        from urllib.parse import quote_plus
        def quote_param(v):
            return quote_plus(str(v))

        imported = 0
        core_totals = {}
        anc_totals = {}

        for r in rows_to_import:
            try:
                event_id = get_or_create_event(r["event"], r["location"])
                comp_year_id = get_or_create_competition_year(event_id, r["year"], r["start_date"], r["end_date"], r["total_teams"])
                # core meat
                if r["meat"] and r["meat"] in ["Chicken","Ribs","Pork","Brisket"]:
                    payload = {
                        "competition_year_id": comp_year_id,
                        "meat": r["meat"],
                        "participant": r["participant"],
                        "score": r["score"],
                        "rank": r["rank"]
                    }
                    rr = supabase_insert("meat_results", payload)
                    if rr.status_code not in (200,201):
                        st.error(f"meat insert error: {rr.status_code} {rr.text}")
                else:
                    # ancillary
                    if r["ancillary_category"]:
                        cat_id = get_or_create_ancillary_category(comp_year_id, r["ancillary_category"])
                        payload = {
                            "competition_year_id": comp_year_id,
                            "category_id": cat_id,
                            "participant": r["participant"],
                            "score": r["score"],
                            "rank": r["rank"]
                        }
                        rr = supabase_insert("ancillary_results", payload)
                        if rr.status_code not in (200,201):
                            st.error(f"ancillary insert error: {rr.status_code} {rr.text}")
                # capture totals to insert later (not now)
                key = comp_year_id

                if r["team_total_score"] is not None or r["team_rank"] is not None:
                    core_totals[key] = {
                        "competition_year_id": key,
                        "total_score": r["team_total_score"],
                        "rank": r["team_rank"]
                    }

                if r["ancillary_team_total"] is not None or r["ancillary_team_rank"] is not None:
                    anc_totals[key] = {
                        "competition_year_id": key,
                        "total_score": r["ancillary_team_total"],
                        "rank": r["ancillary_team_rank"]
                    }

                # # team totals (core)
                # if r["team_total_score"] is not None or r["team_rank"] is not None:
                #     payload = {
                #         "competition_year_id": comp_year_id,
                #         "total_score": r["team_total_score"],
                #         "rank": r["team_rank"]
                #     }
                #     rr = supabase_insert("team_results", payload)
                #     # ignore errors (unique constraint may exist)
                # # ancillary team totals
                # if r["ancillary_team_total"] is not None or r["ancillary_team_rank"] is not None:
                #     payload = {
                #         "competition_year_id": comp_year_id,
                #         "total_score": r["ancillary_team_total"],
                #         "rank": r["ancillary_team_rank"]
                #     }
                #     rr = supabase_insert("ancillary_team_results", payload)
                imported += 1
            except Exception as e:
                st.error(f"Row import error: {e}")
                continue
        # insert core totals
        for key, payload in core_totals.items():
            supabase_upsert(
                "team_results",
                payload,
                on_conflict="competition_year_id"
            )

        # insert ancillary totals
        for key, payload in anc_totals.items():
            supabase_upsert(
                "ancillary_team_results",
                payload,
                on_conflict="competition_year_id"
            )

        st.success(f"Imported {imported} rows.")
