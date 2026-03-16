# JobBot 🤖

**An automated job/internship application engine that runs on your Mac.**

JobBot scrapes multiple job boards daily, uses GPT-4o to write tailored cover letters for each position, and opens a local dashboard where you review each application and launch with one click.

---

## What it does

1. **Scrapes** Indeed, LinkedIn, Wellfound, Handshake, SimplyHired, and Internships.com every morning
2. **Scores** each job by relevance to your profile and location preferences
3. **Drafts** a personalized cover letter, "About Me", and fit summary for the top 10 jobs using GPT-4o
4. **Opens a dashboard** at `localhost:5555` where you can review, edit, and launch each application
5. **Deduplicates** — never shows you the same job twice across days

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.template .env
```

Then open `.env` and fill in your credentials (OpenAI API key required; LinkedIn/Handshake optional).

### 3. First-time setup wizard

Run the dashboard server — it will auto-open the setup wizard on first launch:

```bash
python3 dashboard/server.py
```

Or manually open: [http://localhost:5555/setup](http://localhost:5555/setup)

The wizard will ask for:
- Your name, email, phone, LinkedIn URL
- Resume (upload PDF or paste text)
- Job preferences (type, role, location, dates, industries)
- Job board credentials (LinkedIn, Handshake)
- OpenAI API key and spend limit

### 4. Run the bot

```bash
python3 run_daily.py
```

Or set it to run automatically on macOS login — see **Auto-start** below.

---

## Auto-start on Mac login

```bash
bash setup.sh
```

This installs a launchd agent that runs `run_daily.py` once per day on your first login. The bot won't run a second time on the same day (lock file protection).

---

## Dashboard

Open [http://localhost:5555](http://localhost:5555) after running the bot.

- **Left sidebar** — list of all drafted applications, sorted by fit score
- **Detail pane** — editable cover letter, About Me, pre-fill info, job description
- **Open & Apply** — opens the apply URL in a new tab with your info ready to paste
- **Mark as Sent** — tracks what you've actually sent
- **Date picker** — browse all past days

---

## Customization

### Job queries
Edit `scraper/scrape_jobs.py` → `build_search_queries()` to add or remove query terms.

### Scoring
Edit `drafter/draft_applications.py` → `score_job()` to adjust what the bot prioritizes.

### Location filter
The borough/location filter logic is in `drafter/draft_applications.py` → `is_allowed_location()`. By default it applies only to the location field. Adjust `BOROUGH_WHITELIST` and `UPTOWN_SIGNALS` for your city.

### Spend limit
Set `DAILY_SPEND_LIMIT` in your `.env`. The bot checks your OpenAI usage before and between each generation call. Default: $0.50/day (~10 applications).

---

## Sharing to GitHub (safely)

Before pushing, verify these are in your `.gitignore` (they are by default):

```
.env                    # ← your API keys & passwords
config/profile.json     # ← your personal info
config/resume.txt       # ← your resume
data/                   # ← scraped jobs and applications
logs/                   # ← runtime logs
```

Run this to double-check nothing sensitive is staged:

```bash
git status
git diff --cached
```

---

## Project structure

```
jobbot-public/
├── scraper/
│   └── scrape_jobs.py       # Multi-source job scraper (RSS + HTTP)
├── drafter/
│   ├── draft_applications.py  # AI cover letter + scoring engine
│   └── send_digest.py         # Optional email digest
├── dashboard/
│   ├── server.py              # Flask server (localhost:5555)
│   └── index.html             # Review UI
├── setup/
│   ├── onboarding.html        # Setup wizard UI (5-step form)
│   └── setup_handler.py       # Writes profile.json + .env from form data
├── config/                    # Created by setup wizard (gitignored)
│   ├── profile.json           # Your preferences (auto-generated)
│   └── resume.txt             # Your resume text (auto-generated)
├── data/                      # Runtime data (gitignored)
│   ├── jobs/                  # Scraped job files by date
│   │   └── seen_ids.json      # Dedup memory
│   ├── applications/          # Drafted application files by date
│   └── sent/                  # Sent applications log
├── logs/                      # Log files (gitignored)
├── run_daily.py               # Master runner
├── requirements.txt
├── setup.sh                   # macOS launchd installer
├── .env.template              # Credential template (safe to commit)
└── .gitignore
```

---

## Requirements

- macOS (launchd auto-start) — the core bot works on any OS
- Python 3.9+
- OpenAI API key (GPT-4o) — ~$0.05–0.15/day for 10 applications
- LinkedIn account (optional — improves job results)
- Handshake account (optional — for college students)

---

## Cost estimate

| Usage | Est. cost |
|-------|-----------|
| 10 applications/day (cover letter + about me + fit summary) | ~$0.05–0.15 |
| Monthly | ~$1.50–4.50 |

Set `DAILY_SPEND_LIMIT=0.50` in `.env` as a safety cap.

---

*Built with [Perplexity Computer](https://www.perplexity.ai/computer)*
