# JobBot Audit Fixes + Public Product Hardening
**Date:** 2026-04-01  
**Repo:** job-bot/  
**Approach:** Consolidate → Fix → De-personalize → Ship

---

## Context

JobBot is being shipped as a public product on Leo's portfolio. An external code audit (March 31, 2026) identified 15 issues across critical, high, medium, and low severity. Additionally, the codebase has NYC-specific and Leo-specific logic hardcoded in source files that must be removed before public release. A duplicate directory (`jobbot-public/`) must be merged and deleted.

---

## Phase 0 — Codebase Consolidation

**Goal:** One canonical codebase, zero personal data in source.

### Key finding
`jobbot-public/dashboard/server.py` is the canonical version (685 lines). `job-bot/dashboard/server.py` is old and incomplete (462 lines), missing: `find_app_any_date()`, blocked companies API, response tracking, background scrape runner, `/api/all-applications`, and has a duplicate `_open()` bug in `__main__`. Use jobbot-public as the source for all files, not the other way around.

### Files to copy FROM jobbot-public → job-bot
1. `jobbot-public/dashboard/server.py` → `job-bot/dashboard/server.py` (replaces old version)
2. `jobbot-public/scraper/score_jobs.py` → `job-bot/scraper/score_jobs.py` (missing file)
3. `jobbot-public/START_JOBBOT.command` → `job-bot/START_JOBBOT.command`
4. `jobbot-public/data/blocked_companies.json` → `job-bot/data/blocked_companies.json`

### Verify .gitignore covers all personal/runtime files
- `.env`, `config/profile.json`, `config/resume.txt`
- `data/` (all subdirs), `logs/*.log`, `logs/*.lock`
- `data/jobs/seen_ids.json`

### Cleanup
- Confirm `job-bot/config/` only has `.gitkeep` committed — no personal files
- Delete `jobbot-public/` entirely
- Update `JOBBOT.md` — remove all references to `jobbot-public/`

### What is NOT migrated
Personal runtime files (profile.json, resume.txt, .env, seen_ids.json, data files) are intentionally left behind. New users generate these via the onboarding wizard.

---

## Phase 1 — Critical Fix: score_jobs.py Wiring

**Goal:** Dashboard stops crashing on startup.

### score_jobs.py
Already complete in jobbot-public — just copied in Phase 0. Exports:
- `extract_features(job)` — extracts company_type, role_keywords, industry, source
- `record_feedback(action, job_data)` — updates weights in preferences.json
- `score_job(job, prefs)` — scores a job against learned weights
- `load_preferences()` — loads/initializes preferences.json

### Fix: double extraction bug in server.py `/api/feedback`
Current code (broken):
```python
features = extract_features(job_data_raw)   # extracts features
prefs = record_feedback(action, features)   # then passes features to record_feedback
```
`record_feedback` expects raw job data and re-extracts internally. Fix: remove the `extract_features()` call in the feedback route and pass `job_data_raw` directly:
```python
prefs = record_feedback(action, job_data_raw)
```

### Path verification
`server.py` line 23: `sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))` resolves to `job-bot/scraper/` — correct, no change needed.

---

## Phase 2 — Security Fixes

### 2a. Path Traversal (`dashboard/server.py`)

`load_apps(date_str)` and `save_apps(apps, date_str)` accept unsanitized user input directly into file paths.

**Fix:** Add validator and call it at the top of both functions:
```python
import re
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

def _validate_date_str(date_str: str) -> None:
    if not _DATE_RE.match(date_str):
        raise ValueError(f"Invalid date: {date_str!r}")
```
In the `/api/applications` route, catch `ValueError` and return HTTP 400.

### 2b. .env Injection (`setup/setup_handler.py`)

User-supplied credential values written to `.env` without sanitization. A value containing `\n` would inject additional environment variables.

**Fix:** Add sanitizer and apply to all `credentials.get(...)` calls:
```python
def _sanitize_env_val(val: str) -> str:
    return re.sub(r'[\r\n\x00]', '', str(val))
```

### 2c. CORS (`dashboard/server.py`)

`CORS(app)` allows any origin.

**Fix:**
```python
CORS(app, origins=["http://localhost:5555"])
```

---

## Phase 3 — Spend Guardrail (Fail Closed)

**File:** `drafter/draft_applications.py`, `get_todays_spend()`

Current behavior: returns `0.0` on API error → bot treats day as unspent → spends freely.

**Fix:** Return `float('inf')` on any failure path so `check_spend_limit` halts generation:
```python
# on status != 200:
log.warning("Usage API unavailable — failing closed, halting AI generation")
return float('inf')

# on exception:
log.warning(f"Could not fetch usage: {e} — failing closed, halting AI generation")
return float('inf')
```

---

## Phase 4 — Resilience Fixes

### 4a. File Handle Leak (`run_daily.py`)

Anonymous `open()` in `subprocess.Popen` is never assigned or managed.

**Fix:** Assign to named variable. The handle stays open intentionally (subprocess stdout) but is now explicit:
```python
dashboard_log = open(LOG_DIR / "dashboard.log", "a")
subprocess.Popen(
    [sys.executable, str(ROOT / "dashboard" / "server.py")],
    stdout=dashboard_log,
    stderr=subprocess.STDOUT,
)
```

### 4b. Atomic Writes

Direct `.write_text()` on data files will corrupt JSON if the process crashes mid-write.

**Fix:** Add shared utility `atomic_write(path, data)` at the top of each affected module:
```python
def atomic_write(path: Path, data: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)  # atomic rename on POSIX
```

Apply to all JSON data writes:
- `scraper/scrape_jobs.py` — `save_seen()`
- `drafter/draft_applications.py` — `TODAY_APPS_FILE.write_text(...)`
- `scraper/score_jobs.py` — `save_preferences()`
- `dashboard/server.py` — `save_apps()`, `sent_log.write_text(...)`

### 4c. JSON Read Error Handling

Bare `json.loads(f.read_text())` calls throughout will crash with `JSONDecodeError` on corrupted files.

**Fix per call site:**

| Location | Behavior on error |
|----------|------------------|
| `scraper/scrape_jobs.py` `load_seen()` | Log warning, return `set()` |
| `dashboard/server.py` `load_apps()` | Log warning, return `[]` |
| `dashboard/server.py` sent_log reads (2x) | Return `[]` silently |
| `dashboard/server.py` `application_history()` loop | Already has try/except, confirm |
| `drafter/draft_applications.py` `load_profile()` | Re-raise with message: `"profile.json is missing or corrupted — re-run setup at http://localhost:5555/setup"` |
| `scraper/score_jobs.py` `load_preferences()` | Already has try/except, confirmed correct |

---

## Phase 5 — Minor Fixes

| Issue | File | Fix |
|-------|------|-----|
| Unbalanced paren in log string | `drafter/draft_applications.py:55` | Add missing `)` to f-string: `(limit: ${DAILY_SPEND_LIMIT})` |
| Module-level date evaluation | `drafter/draft_applications.py:70-71` | Move `TODAY`, `TODAY_JOBS_FILE`, `TODAY_APPS_FILE` inside `run_drafter()` — evaluate at call time, not import time |
| Stale User-Agent | `scraper/scrape_jobs.py:53` | Update Chrome version from `122.0.0.0` to `124.0.0.0` |
| MD5 → SHA256 for dedup | `scraper/scrape_jobs.py:148` | `hashlib.md5` → `hashlib.sha256` |
| Unused dependencies | `requirements.txt` | Remove `selenium>=4.18.0` and `webdriver-manager>=4.0.1` |

---

## Phase 6 — Scraper Cleanup + New Sources

### Remove (SPA — return zero results with requests)
- `scrape_wellfound` — full React SPA
- `scrape_handshake_public` — SPA + login wall
- `scrape_internships_dot_com` — SPA

### Keep
- `scrape_indeed_rss` — RSS, highly reliable
- `scrape_linkedin_public` — best-effort, silently returns 0 if blocked (acceptable)
- `scrape_simplyhired` — server-side rendered, selectors reasonable

### Add

**RemoteOK** (`scraper/scrape_jobs.py`)
- Endpoint: `https://remoteok.com/api` — returns JSON array of job objects
- Fields map directly: `position` → title, `company`, `location`, `description`, `url`
- Filter by tags matching user's role_types from profile
- No auth, no parsing, no fragility
- Limit: 15 jobs

**Built In NYC** (`scraper/scrape_jobs.py`)
- URL: `https://www.builtinnyc.com/jobs`
- Static HTML, no JS rendering
- Selectors: `div.job-card`, title/company/link from standard card structure
- Only runs when `location_preference` contains `"new york"` (case-insensitive)
- Limit: 10 jobs

### Updated `run_scraper()` order
```python
scrapers = [
    (scrape_indeed_rss,      25),
    (scrape_linkedin_public, 15),
    (scrape_remoteok,        15),
    (scrape_simplyhired,     10),
    (scrape_builtinnyc,      10),  # only if NYC
]
target = 50
```

---

## Phase 7 — De-personalization

### 7a. Remove NYC hardcoding from `draft_applications.py`

**Delete entirely:**
- `BOROUGH_WHITELIST`, `PRIORITY_BOROUGHS`, `UPTOWN_SIGNALS` constants
- `is_allowed_location(job)` function
- `borough_score_bonus(job)` function
- The location filter call in `run_drafter()`

**Replace with generic location filter** `is_allowed_location(job, profile)`:
```python
def is_allowed_location(job: dict, profile: dict) -> bool:
    pref = (profile.get("location_preference") or "").lower().strip()
    if not pref or "remote" in pref:
        return True  # accept everything if no preference or remote
    job_loc = (job.get("location") or "").lower()
    if not job_loc:
        return True  # blank location — give benefit of the doubt
    # Extract city name (first word before comma) for flexible matching
    city = pref.split(",")[0].strip()
    return city in job_loc
```

Update `run_drafter()` to call `is_allowed_location(j, profile)` with profile passed in.

### 7b. Genericize `score_job()` keyword lists

Remove Leo-specific boosts from `score_job()` in `draft_applications.py`:
- **Remove from good_terms:** `"vc"`, `"venture"`, `"founder"`, `"entrepreneur"` — too niche as universal defaults
- **Keep as generic entry-level defaults:** `"intern"`, `"internship"`, `"startup"`, `"growth"`, `"marketing"`, `"sales"`, `"operations"`, `"product"`, `"generalist"`, `"strategy"`, `"analyst"`, `"associate"`, `"digital"`, `"technology"`, `"content"`, `"brand"`
- Remove `borough_score_bonus()` call (deleted in 7a)
- The preference learning system (score_jobs.py) will personalize over time — this heuristic is just a neutral day-1 baseline

### 7c. Update README.md

Rewrite as a proper public-facing product README:
- What JobBot does (1-paragraph description)
- Requirements (Python 3.10+, OpenAI API key)
- Setup instructions (clone → `pip install -r requirements.txt` → `python dashboard/server.py` → complete wizard)
- How it works (scrape → score → draft → review → apply)
- How preference learning works (approve/skip trains your personal model)
- Data privacy note (all data local, nothing leaves your machine except OpenAI API calls)
- No personal references

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `scraper/score_jobs.py` | New file (copied from jobbot-public) |
| `dashboard/server.py` | Fix feedback route, path traversal, CORS, JSON error handling, atomic writes |
| `setup/setup_handler.py` | .env injection fix |
| `drafter/draft_applications.py` | Spend guardrail, module-level date, log paren, remove NYC hardcode, genericize score_job |
| `scraper/scrape_jobs.py` | Remove 3 dead scrapers, add RemoteOK + BuiltInNYC, SHA256, User-Agent, atomic writes, JSON error handling |
| `run_daily.py` | File handle fix |
| `requirements.txt` | Remove selenium + webdriver-manager |
| `README.md` | Full rewrite for public product |
| `JOBBOT.md` | Remove jobbot-public references |
| `jobbot-public/` | Deleted |

---

## Out of Scope

- Dashboard UI changes
- Cover letter prompt tuning
- Onboarding wizard UI
- launchd scheduler
- Email digest localhost links (noted in README as known limitation)
- Unit tests
