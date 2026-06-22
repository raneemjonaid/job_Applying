# Job Agent — Stage 1: Discovery

Finds job listings and saves them to `jobs.json` for the next stage (matching).

## Setup

```bash
pip install -r requirements.txt --break-system-packages
export ANTHROPIC_API_KEY=your_key_here   # needed only for manual links
```

## Configure sources

Copy `sources.example.json` to `sources.json` and edit it:

- `greenhouse`: company "board token" — find it in their careers URL, e.g. `boards.greenhouse.io/nesr` → token is `nesr`
- `lever`: company slug — find it in their careers URL, e.g. `jobs.lever.co/netflix` → slug is `netflix`
- `manual_links`: paste any job URL (LinkedIn, Indeed, Bayt, a company's own site). One page fetch per link, no login, no crawling — Claude reads the page and pulls out title/company/location/description.

```json
{
  "greenhouse": ["nesr"],
  "lever": [],
  "manual_links": ["https://www.linkedin.com/jobs/view/123456"]
}
```

## Run

```bash
python job_discovery.py --config sources.json --output jobs.json
```

## Notes / honesty check

- Greenhouse and Lever calls hit their public, documented job-board APIs — not scraping, just normal API requests.
- LinkedIn job pages are often partially hidden behind a login wall when fetched logged-out, so manual-link results from LinkedIn may have a thinner description than what you'd see logged in. This is intentional: the script never logs in or automates your session, to stay clear of LinkedIn's bot-detection and avoid any risk to your account.
- Please run a real pass on your own machine/environment and sanity-check the first batch of output before trusting it for later stages.

## Next stage

Once you have a `jobs.json` you're happy with, the next piece is the matching layer: scoring each job against your profile and goals so the pipeline only carries forward the ones worth tailoring a CV for.
