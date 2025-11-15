# migrate_excel_to_supabase.py
import pandas as pd
from pathlib import Path
from datetime import datetime
from supabase_client import supabase_get, supabase_insert
import time

CORE_MEATS = {"Chicken", "Ribs", "Pork", "Brisket"}

EXCEL_FILE = "bbq_results.xlsx"   # change to your filename

def parse_date_range(text):
    # Accepts "YYYY-MM-DD to YYYY-MM-DD" or single date "YYYY-MM-DD"
    if pd.isna(text):
        return None, None
    text = str(text).strip()
    if "to" in text:
        parts = [p.strip() for p in text.split("to")]
        try:
            s = pd.to_datetime(parts[0]).date()
            e = pd.to_datetime(parts[1]).date()
            return s, e
        except Exception:
            return None, None
    else:
        try:
            d = pd.to_datetime(text).date()
            return d, d
        except Exception:
            return None, None

def ensure_competition(row, cache):
    # key by (name, start_date, end_date, location)
    name = str(row.get("Competition") or row.get("Competition Name") or row.get("Location") or "").strip()
    comp_dates = row.get("Competition Dates") or row.get("Competition Date") or row.get("Dates") or None
    start_date, end_date = parse_date_range(comp_dates)
    location = str(row.get("Location") or "").strip()
    total_teams = int(row.get("Total Teams") or 0)
    key = (name, start_date, end_date, location, total_teams)
    if key in cache:
        return cache[key]

    comp_payload = {
        "name": name,
        "location": location,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "total_teams": total_teams
    }
    resp = supabase_insert("competitions", comp_payload)
    if resp.status_code not in (200,201):
        raise RuntimeError(f"Error creating competition: {resp.status_code} {resp.text}")
    comp_row = resp.json()[0]
    comp_id = comp_row["id"]
    cache[key] = comp_id
    return comp_id

def ensure_ancillary_category(comp_id, cat_name, cache):
    key = (comp_id, cat_name)
    if key in cache:
        return cache[key]
    payload = {"competition_id": comp_id, "category_name": cat_name}
    resp = supabase_insert("ancillary_categories", payload)
    if resp.status_code not in (200,201):
        # Could be unique violation if category already exists, attempt to fetch
        get_resp = supabase_get("ancillary_categories")
        if get_resp.status_code == 200:
            for r in get_resp.json():
                if r["competition_id"] == comp_id and r["category_name"].lower() == cat_name.lower():
                    cache[key] = r["id"]
                    return r["id"]
        raise RuntimeError(f"Error creating ancillary category: {resp.status_code} {resp.text}")
    cat_row = resp.json()[0]
    cache[key] = cat_row["id"]
    return cat_row["id"]

def import_excel(file_path):
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(file_path)
    xls = pd.ExcelFile(p)
    # combine all valid sheets into single dataframe
    frames = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        frames.append(df)
    df_all = pd.concat(frames, ignore_index=True, sort=False)

    # normalize column names (simple)
    df_all.columns = [c.strip() for c in df_all.columns]

    # caches
    comp_cache = {}
    ancillary_cache = {}

    # iterate rows
    for idx, row in df_all.iterrows():
        # Skip rows with no useful data
        if pd.isna(row.get("Year")) and pd.isna(row.get("Competition")):
            continue

        try:
            competition_id = ensure_competition(row, comp_cache)
        except Exception as e:
            print("Competition create error:", e)
            continue

        year = int(row.get("Year")) if not pd.isna(row.get("Year")) else None

        meat_field = row.get("Meat") or row.get("Category") or row.get("Submission") or None
        participant = row.get("Participant") or row.get("Member") or row.get("Cook") or None
        score = row.get("Score") if not pd.isna(row.get("Score")) else None
        rank = int(row.get("Rank")) if (not pd.isna(row.get("Rank"))) else None

        # Team totals handling
        team_total = row.get("Team Total") or row.get("Team Score") or row.get("Team_Score") or None
        team_rank = row.get("Team Rank") or row.get("Team_Rank") or None

        # Ancillary team totals handling (sides)
        ancillary_team_total = row.get("Sides Team Score") or row.get("Side Total") or None
        ancillary_team_rank = row.get("Sides Team Rank") or row.get("Side Rank") or None

        # Insert core meat result
        if meat_field and str(meat_field).strip() in CORE_MEATS:
            meat_payload = {
                "competition_id": competition_id,
                "year": year,
                "meat": str(meat_field).strip(),
                "participant": participant,
                "score": float(score) if score is not None else None,
                "rank": int(rank) if rank is not None else None
            }
            resp = supabase_insert("meat_results", meat_payload)
            if resp.status_code not in (200,201):
                print("meat insert error:", resp.status_code, resp.text)

        else:
            # Treat as ancillary submission (if meat_field present)
            if meat_field and str(meat_field).strip():
                cat_name = str(meat_field).strip()
                try:
                    cat_id = ensure_ancillary_category(competition_id, cat_name, ancillary_cache)
                except Exception as e:
                    print("ancillary category error:", e)
                    continue
                ancillary_payload = {
                    "competition_id": competition_id,
                    "category_id": cat_id,
                    "participant": participant,
                    "score": float(score) if score is not None else None,
                    "rank": int(rank) if rank is not None else None
                }
                resp = supabase_insert("ancillary_results", ancillary_payload)
                if resp.status_code not in (200,201):
                    print("ancillary insert error:", resp.status_code, resp.text)

        # Insert team_results row if team_total or team_rank present (one per competition expected)
        if (team_total is not None) or (team_rank is not None):
            # Try insert; if exists, skip or update
            # We'll attempt insert; unique constraint on competition_id will error if exists
            team_payload = {
                "competition_id": competition_id,
                "total_score": float(team_total) if team_total is not None else None,
                "rank": int(team_rank) if team_rank is not None else None
            }
            resp = supabase_insert("team_results", team_payload)
            if resp.status_code not in (200,201):
                # ignore duplicates/errors
                pass

        # Insert ancillary_team_results if present
        if (ancillary_team_total is not None) or (ancillary_team_rank is not None):
            at_payload = {
                "competition_id": competition_id,
                "total_score": float(ancillary_team_total) if ancillary_team_total is not None else None,
                "rank": int(ancillary_team_rank) if ancillary_team_rank is not None else None
            }
            resp = supabase_insert("ancillary_team_results", at_payload)
            if resp.status_code not in (200,201):
                # ignore duplicates/errors
                pass

        time.sleep(0.05)  # gentle throttle

    print("Import completed.")

if __name__ == "__main__":
    import sys
    fname = sys.argv[1] if len(sys.argv) > 1 else EXCEL_FILE
    import_excel = import_excel if False else None
    # call import function
    try:
        import_excel = import_excel  # placeholder to satisfy static analyzers
    except:
        pass

    # Run actual import
    from migrate_excel_to_supabase import import_excel as runner
    runner(fname)
