"""
DataPilot Job Agent — Stage 2: Matching

Scores each job in jobs.json (Stage 1 output) against profile.json using
Claude, and writes out only the jobs worth pursuing, ranked by fit.

Setup:
    export ANTHROPIC_API_KEY=your_key_here

Usage:
    python job_matching.py --jobs jobs.json --profile profile.json --output matches.json
"""

import json
import re
import os
import time
import argparse
from dataclasses import dataclass, asdict
from typing import List

import anthropic

MATCH_PROMPT = """You are screening a job posting against a candidate's profile.
Respond with ONLY valid JSON, no preamble, no markdown fences:

{{
  "score": <integer 0-100, how well this job fits the candidate>,
  "verdict": "strong" | "possible" | "skip",
  "reason": "one or two sentences explaining the score, referencing specific skills/requirements"
}}

Score based on: title/seniority alignment, required skills overlap, location fit, and any dealbreakers.
A "strong" match is 70+, "possible" is 40-69, "skip" is below 40.

CANDIDATE PROFILE:
{profile}

JOB POSTING:
Title: {title}
Company: {company}
Location: {location}
Description: {description}
"""


@dataclass
class JobMatch:
    title: str
    company: str
    location: str
    url: str
    source: str
    score: int
    verdict: str
    reason: str


def score_job(client, profile_text: str, job: dict) -> JobMatch:
    prompt = MATCH_PROMPT.format(
        profile=profile_text,
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location") or "Not specified",
        description=(job.get("description") or "")[:4000],
    )
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```json|```$", "", raw).strip()
    parsed = json.loads(raw)

    return JobMatch(
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location") or "",
        url=job.get("url", ""),
        source=job.get("source", ""),
        score=int(parsed.get("score", 0)),
        verdict=parsed.get("verdict", "skip"),
        reason=parsed.get("reason", ""),
    )


def run(jobs: List[dict], profile: dict, min_score: int) -> List[JobMatch]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY not set — matching requires Claude.")
    client = anthropic.Anthropic(api_key=api_key)
    profile_text = json.dumps(profile, indent=2)

    matches: List[JobMatch] = []
    for job in jobs:
        try:
            match = score_job(client, profile_text, job)
        except (json.JSONDecodeError, anthropic.APIError) as e:
            print(f"[match] {job.get('url', '?')}: {e}")
            continue
        if match.score >= min_score:
            matches.append(match)
        time.sleep(0.5)

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches


def main():
    parser = argparse.ArgumentParser(description="DataPilot Job Agent — Matching stage")
    parser.add_argument("--jobs", default="jobs.json", help="Path to Stage 1 jobs JSON")
    parser.add_argument("--profile", default="profile.json", help="Path to candidate profile JSON")
    parser.add_argument("--output", default="matches.json", help="Path to write ranked matches")
    parser.add_argument("--min-score", type=int, default=40, help="Minimum score to keep (default 40)")
    args = parser.parse_args()

    with open(args.jobs, "r", encoding="utf-8") as f:
        jobs = json.load(f)
    with open(args.profile, "r", encoding="utf-8") as f:
        profile = json.load(f)

    matches = run(jobs, profile, args.min_score)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump([asdict(m) for m in matches], f, indent=2, ensure_ascii=False)

    print(f"Matched {len(matches)}/{len(jobs)} job(s) -> {args.output}")


if __name__ == "__main__":
    main()
