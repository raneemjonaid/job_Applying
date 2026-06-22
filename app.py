"""
DataPilot Job Agent — Interface

A local Streamlit UI to manage the discovery -> matching pipeline:
edit sources.json, run job_discovery.py, run job_matching.py, and
browse the resulting jobs/matches in a table.

Run:
    streamlit run app.py
"""

import json
import os
import subprocess
import sys

import streamlit as st

SOURCES_PATH = "sources.json"
PROFILE_PATH = "profile.json"
JOBS_PATH = "jobs.json"
MATCHES_PATH = "matches.json"

st.set_page_config(page_title="Job Agent", layout="wide")
st.title("Job Agent")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


tab_sources, tab_discover, tab_match, tab_results = st.tabs(
    ["1. Sources", "2. Discover", "3. Match", "4. Results"]
)

# ---------------------------------------------------------------------------
# Tab 1: Sources
# ---------------------------------------------------------------------------
with tab_sources:
    st.subheader("Job sources")
    sources = load_json(SOURCES_PATH, {"greenhouse": [], "lever": [], "manual_links": []})

    greenhouse_text = st.text_area(
        "Greenhouse board tokens (one per line)",
        value="\n".join(sources.get("greenhouse", [])),
        help="From a careers URL like boards.greenhouse.io/<token>",
    )
    lever_text = st.text_area(
        "Lever company slugs (one per line)",
        value="\n".join(sources.get("lever", [])),
        help="From a careers URL like jobs.lever.co/<slug>",
    )
    manual_text = st.text_area(
        "Manual job links (one per line)",
        value="\n".join(sources.get("manual_links", [])),
        help="LinkedIn, Indeed, Bayt, or any company site job posting URL",
    )

    if st.button("Save sources.json"):
        new_sources = {
            "greenhouse": [t.strip() for t in greenhouse_text.splitlines() if t.strip()],
            "lever": [t.strip() for t in lever_text.splitlines() if t.strip()],
            "manual_links": [t.strip() for t in manual_text.splitlines() if t.strip()],
        }
        save_json(SOURCES_PATH, new_sources)
        st.success(f"Saved {SOURCES_PATH}")

# ---------------------------------------------------------------------------
# Tab 2: Discover
# ---------------------------------------------------------------------------
with tab_discover:
    st.subheader("Run Stage 1: Discovery")
    st.caption("Pulls Greenhouse/Lever listings and parses manual links into jobs.json")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.warning("ANTHROPIC_API_KEY is not set in this environment — manual links will be saved unparsed.")

    if st.button("Run discovery"):
        if not os.path.exists(SOURCES_PATH):
            st.error(f"{SOURCES_PATH} not found — save your sources first.")
        else:
            with st.spinner("Running job_discovery.py..."):
                result = subprocess.run(
                    [sys.executable, "job_discovery.py", "--config", SOURCES_PATH, "--output", JOBS_PATH],
                    capture_output=True, text=True,
                )
            st.code(result.stdout + result.stderr or "(no output)")
            if result.returncode == 0:
                st.success("Discovery finished — see Results tab.")
            else:
                st.error("Discovery failed — see output above.")

# ---------------------------------------------------------------------------
# Tab 3: Match
# ---------------------------------------------------------------------------
with tab_match:
    st.subheader("Run Stage 2: Matching")
    st.caption("Scores jobs.json against profile.json using Claude")

    min_score = st.slider("Minimum score to keep", 0, 100, 40)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.warning("ANTHROPIC_API_KEY is not set in this environment — matching will fail.")
    if not os.path.exists(PROFILE_PATH):
        st.warning(f"{PROFILE_PATH} not found.")

    if st.button("Run matching"):
        if not os.path.exists(JOBS_PATH):
            st.error(f"{JOBS_PATH} not found — run discovery first.")
        else:
            with st.spinner("Running job_matching.py..."):
                result = subprocess.run(
                    [sys.executable, "job_matching.py", "--jobs", JOBS_PATH, "--profile", PROFILE_PATH,
                     "--output", MATCHES_PATH, "--min-score", str(min_score)],
                    capture_output=True, text=True,
                )
            st.code(result.stdout + result.stderr or "(no output)")
            if result.returncode == 0:
                st.success("Matching finished — see Results tab.")
            else:
                st.error("Matching failed — see output above.")

# ---------------------------------------------------------------------------
# Tab 4: Results
# ---------------------------------------------------------------------------
with tab_results:
    st.subheader("Discovered jobs")
    jobs = load_json(JOBS_PATH, [])
    if jobs:
        st.dataframe(jobs, use_container_width=True)
    else:
        st.info(f"No {JOBS_PATH} yet — run discovery.")

    st.subheader("Matches")
    matches = load_json(MATCHES_PATH, [])
    if matches:
        st.dataframe(matches, use_container_width=True)
    else:
        st.info(f"No {MATCHES_PATH} yet — run matching.")
