# JobBot

Automated job application assistant. Scrapes job boards every morning, scores listings against your profile with AI, drafts tailored cover letters, and surfaces everything in a local review dashboard — ready for 5-minute review and one-click apply.

---

## What It Does

1. **Scrapes** Indeed, LinkedIn, RemoteOK, SimplyHired, and Built In NYC (NYC users only) each morning
2. **Scores** each listing for fit using keyword heuristics + a preference learning system that improves as you approve/skip jobs
3. **Drafts** a tailored cover letter and "About Me" for each top listing using GPT-4o
4. **Surfaces** everything in a local dashboard at `http://localhost:5555` for review
5. **Tracks** every application you send and learns your preferences over time

---

## Requirements

- macOS (the launcher uses launchd; the dashboard runs on any OS)
- Python 3.10+
- An [OpenAI API key](https://platform.openai.com/api-keys) (GPT-4o access)

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/LJSNYC/jobbot.git
cd jobbot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the dashboard
python dashboard/server.py
```

Open `http://localhost:5555` — the setup wizard will guide you through entering your profile, resume, and API key. This takes about 2 minutes.

---

## Daily Usage

**Manual run:**
```bash
python run_daily.py
```

**Automatic (macOS launchd):**
Double-click `START_JOBBOT.command` to register the daily 7am run with macOS. JobBot will scrape, draft, and open the dashboard automatically each morning.

---

## How It Works

### Scraping
JobBot scrapes job boards using `requests` + `BeautifulSoup`. Sources:
- **Indeed** — RSS feed, highly reliable
- **LinkedIn** — public job search (best-effort; may return fewer results if rate-limited)
- **RemoteOK** — public JSON API, reliable
- **SimplyHired** — HTML scraping
- **Built In NYC** — NYC startup/tech jobs (only runs if your location is New York)

### Scoring
Each job gets two scores:
- **Fit score (0–10)** — heuristic based on title/description keywords matching your target roles
- **Preference score** — learned from your approve/skip actions in the dashboard

### Preference Learning
Every time you approve or skip a job in the dashboard, JobBot updates a local `preferences.json` file with weights for: company type, role keywords, industry, and source. These weights are applied to future job scores — the more you use it, the better the recommendations get.

### Cover Letters
GPT-4o generates a 3-paragraph cover letter tailored to each specific job and company. Letters are editable in the dashboard before you apply.

---

## Data & Privacy

All data is stored locally on your machine:
- `config/profile.json` — your profile
- `config/resume.txt` — your resume text
- `.env` — your API key
- `data/` — scraped jobs, drafted applications, sent log
- `data/preferences.json` — your learned preferences

No data is sent anywhere except to the OpenAI API for cover letter generation (billed to your API key). There is no backend, no account, no tracking.

---

## Cost

JobBot caps daily OpenAI spending at $0.45 by default (configurable in setup). A typical 10-application day costs $0.10–$0.25.

---

## Known Limitations

- LinkedIn scraping is best-effort — may return zero results if rate-limited
- The email digest links point to `localhost:5555` — not useful on mobile
- No hosted version — the dashboard is local only
