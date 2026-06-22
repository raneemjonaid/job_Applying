"""
DataPilot Job Agent — Stage 1: Discovery

Pulls job listings from:
  - Greenhouse (public JSON API, no auth needed)
  - Lever (public JSON API, no auth needed)
  - Manual links (LinkedIn, Indeed, Bayt, any company site) — fetches ONE page
    per link (same as a human clicking it) and uses Claude to extract structured
    fields from the raw text. No login, no crawling, no LinkedIn automation.

Output: a single JSON file of job listings, ready for Stage 2 (matching).

Setup:
    pip install requests beautifulsoup4 anthropic --break-system-packages
    export ANTHROPIC_API_KEY=your_key_here

Usage:
    python job_discovery.py --config sources.json --output jobs.json
"""

import json
import re
import os
import time
import argparse
from dataclasses import dataclass, asdict
from typing import Optional, List

import requests
from bs4 import BeautifulSoup

try:
    import anthropic
except ImportError:
    anthropic = None


@dataclass
class JobListing:
    title: str
    company: str
    location: Optional[str]
    url: str
    description: str
    source: str  # "greenhouse" | "lever" | "manual"
    job_id: Optional[str] = None

    def dedupe_key(self) -> str:
        return f"{self.company.lower()}::{self.title.lower()}::{self.location or ''}".strip()


# ---------------------------------------------------------------------------
# Greenhouse
# ---------------------------------------------------------------------------

def fetch_greenhouse(board_token: str) -> List[JobListing]:
    """
    Greenhouse exposes a public, documented job board API — no auth, no scraping.
    Find a company's token from their careers page URL: boards.greenhouse.io/<token>
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    jobs: List[JobListing] = []
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for j in data.get("jobs", []):
            desc_text = BeautifulSoup(j.get("content", ""), "html.parser").get_text(" ", strip=True)
            jobs.append(JobListing(
                title=j.get("title", ""),
                company=board_token,
                location=(j.get("location") or {}).get("name"),
                url=j.get("absolute_url", ""),
                description=desc_text,
                source="greenhouse",
                job_id=str(j.get("id")),
            ))
    except requests.RequestException as e:
        print(f"[greenhouse] {board_token}: {e}")
    return jobs


# ---------------------------------------------------------------------------
# Lever
# ---------------------------------------------------------------------------

def fetch_lever(company_slug: str) -> List[JobListing]:
    """
    Lever also exposes a public JSON API per company.
    Find the slug from their careers page URL: jobs.lever.co/<slug>
    """
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    jobs: List[JobListing] = []
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for j in data:
            raw_desc = j.get("descriptionPlain") or j.get("description", "")
            desc_text = BeautifulSoup(raw_desc, "html.parser").get_text(" ", strip=True)
            jobs.append(JobListing(
                title=j.get("text", ""),
                company=company_slug,
                location=(j.get("categories") or {}).get("location"),
                url=j.get("hostedUrl", ""),
                description=desc_text,
                source="lever",
                job_id=j.get("id"),
            ))
    except requests.RequestException as e:
        print(f"[lever] {company_slug}: {e}")
    return jobs


# ---------------------------------------------------------------------------
# Manual link (LinkedIn, Indeed, Bayt, individual company sites)
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You will be given the raw visible text of a job posting web page.
Extract the job details and respond with ONLY valid JSON, no preamble, no markdown fences:

{{
  "title": "...",
  "company": "...",
  "location": "... or null",
  "description": "concise plain-text summary, max 500 words"
}}

If a field cannot be found, use null. Page text:
---
{page_text}
---"""


def fetch_manual_link(url: str, client) -> Optional[JobListing]:
    """
    For sites without a public API. Fetches ONE page (same as a human clicking
    the link) and uses Claude to pull structured fields out of the raw text —
    avoids writing a brittle parser per site.

    Note: LinkedIn often hides the full description behind a login wall for
    logged-out requests, so results from LinkedIn links may be partial. That's
    intentional — this script never logs in or simulates a session.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; job-research-bot/1.0)"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[manual] {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    page_text = soup.get_text(" ", strip=True)[:8000]

    if client is None:
        print(f"[manual] No ANTHROPIC_API_KEY set — storing raw text only for {url}")
        return JobListing(title="(unparsed)", company="(unparsed)", location=None,
                           url=url, description=page_text[:1000], source="manual")

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(page_text=page_text)}],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```json|```$", "", raw).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[manual] Could not parse extraction for {url}")
        return None

    return JobListing(
        title=parsed.get("title") or "(unknown)",
        company=parsed.get("company") or "(unknown)",
        location=parsed.get("location"),
        url=url,
        description=parsed.get("description") or "",
        source="manual",
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(config: dict) -> List[JobListing]:
    all_jobs: List[JobListing] = []

    for token in config.get("greenhouse", []):
        all_jobs.extend(fetch_greenhouse(token))
        time.sleep(0.5)

    for slug in config.get("lever", []):
        all_jobs.extend(fetch_lever(slug))
        time.sleep(0.5)

    manual_links = config.get("manual_links", [])
    if manual_links:
        client = None
        if anthropic is None:
            print("anthropic package not installed — run: pip install anthropic --break-system-packages")
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                client = anthropic.Anthropic(api_key=api_key)
            else:
                print("ANTHROPIC_API_KEY not set — manual links will be saved unparsed.")

        for link in manual_links:
            job = fetch_manual_link(link, client)
            if job:
                all_jobs.append(job)
            time.sleep(1)

    seen = set()
    deduped: List[JobListing] = []
    for j in all_jobs:
        key = j.dedupe_key()
        if key not in seen:
            seen.add(key)
            deduped.append(j)

    return deduped


def main():
    parser = argparse.ArgumentParser(description="DataPilot Job Agent — Discovery stage")
    parser.add_argument("--config", default="sources.json", help="Path to sources config JSON")
    parser.add_argument("--output", default="jobs.json", help="Path to write discovered jobs")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    jobs = run(config)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump([asdict(j) for j in jobs], f, indent=2, ensure_ascii=False)

    print(f"Discovered {len(jobs)} job(s) -> {args.output}")


if __name__ == "__main__":
    main()
