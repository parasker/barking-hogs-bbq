# supabase_client.py
import os
import requests
import streamlit as st
from urllib.parse import quote_plus

# Support both local script env and Streamlit secrets
def _get_config():
    url = None
    key = None
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Supabase config not found in st.secrets or environment variables.")
    return url.rstrip('/'), key

SUPABASE_URL, SUPABASE_KEY = None, None
try:
    SUPABASE_URL, SUPABASE_KEY = _get_config()
except Exception:
    # defer raising until called
    pass

HEADERS = lambda: {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def supabase_get(table, params=""):
    global SUPABASE_URL, SUPABASE_KEY
    if not SUPABASE_URL or not SUPABASE_KEY:
        SUPABASE_URL, SUPABASE_KEY = _get_config()
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url = f"{url}?{params}"
    resp = requests.get(url, headers=HEADERS())
    return resp

def supabase_insert(table, record):
    global SUPABASE_URL, SUPABASE_KEY
    if not SUPABASE_URL or not SUPABASE_KEY:
        SUPABASE_URL, SUPABASE_KEY = _get_config()
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.post(url, json=record, headers={**HEADERS(), "Prefer": "return=representation"})
    return resp

def supabase_upsert(table, record, on_conflict=None):
    global SUPABASE_URL, SUPABASE_KEY
    if not SUPABASE_URL or not SUPABASE_KEY:
        SUPABASE_URL, SUPABASE_KEY = _get_config()
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = ""
    if on_conflict:
        params = f"?on_conflict={quote_plus(on_conflict)}"
    resp = requests.post(url + params, json=record, headers={**HEADERS(), "Prefer": "resolution=merge-duplicates,return=representation"})
    return resp

def supabase_delete(table, params):
    global SUPABASE_URL, SUPABASE_KEY
    if not SUPABASE_URL or not SUPABASE_KEY:
        SUPABASE_URL, SUPABASE_KEY = _get_config()
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    resp = requests.delete(url, headers=HEADERS())
    return resp
