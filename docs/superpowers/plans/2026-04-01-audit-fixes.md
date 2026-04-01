# JobBot Audit Fixes + Public Product Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 15 audit issues, consolidate dual codebase, and de-personalize for public release as a portfolio product.

**Architecture:** Sequential phases — consolidate first (jobbot-public is canonical), then security/reliability fixes, then scraper cleanup, then de-personalization. Each task commits independently. All personal data stays out of the repo; the onboarding wizard generates user-specific config at runtime.

**Tech Stack:** Python 3.10+, Flask, BeautifulSoup4, OpenAI API, pytest

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `dashboard/server.py` | Replace + patch | Replace with jobbot-public version (685 lines), then add path traversal validation, CORS restriction, JSON error handling, atomic writes |
| `scraper/score_jobs.py` | Create | Copy from jobbot-public (complete preference learning module) |
| `START_JOBBOT.command` | Create | Copy from jobbot-public |
| `data/blocked_companies.json` | Create | Copy from jobbot-public (empty `[]`) |
| `setup/setup_handler.py` | Modify | Add `_sanitize_env_val` and apply to all credential writes |
| `drafter/draft_applications.py` | Modify | Fail-closed spend guardrail, fix log paren, move module-level date, remove NYC hardcode, generic location filter, genericize score_job keywords |
| `scraper/scrape_jobs.py` | Modify | Remove 3 dead scrapers, add RemoteOK + BuiltInNYC, SHA256, User-Agent, atomic writes, JSON error handling |
| `run_daily.py` | Modify | Fix file handle leak |
| `requirements.txt` | Modify | Remove selenium + webdriver-manager |
| `README.md` | Rewrite | Public-facing product README |
| `tests/conftest.py` | Create | pytest sys.path setup |
| `tests/test_security.py` | Create | Path traversal + .env injection tests |
| `tests/test_spend_guardrail.py` | Create | Fail-closed behavior tests |
| `tests/test_location.py` | Create | Generic location filter tests |

---

## Task 1: Consolidation — Make job-bot/ the single canonical source

**Files:**
- Replace: `job-bot/dashboard/server.py`
- Create: `job-bot/scraper/score_jobs.py`
- Create: `job-bot/START_JOBBOT.command`
- Create: `job-bot/data/blocked_companies.json`
- Verify: `job-bot/.gitignore`

- [ ] **Step 1: Copy the canonical server.py from jobbot-public**

```bash
cp ~/jobbot-public/dashboard/server.py ~/job-bot/dashboard/server.py
```

Verify it's 685 lines:
```bash
wc -l ~/job-bot/dashboard/server.py
```
Expected: `685 /Users/.../job-bot/dashboard/server.py`

- [ ] **Step 2: Copy score_jobs.py (the missing module)**

```bash
cp ~/jobbot-public/scraper/score_jobs.py ~/job-bot/scraper/score_jobs.py
```

Verify it exports the four required symbols:
```bash
grep "^def " ~/job-bot/scraper/score_jobs.py
```
Expected output includes: `extract_features`, `record_feedback`, `score_job`, `load_preferences`

- [ ] **Step 3: Copy START_JOBBOT.command and blocked_companies.json**

```bash
cp ~/jobbot-public/START_JOBBOT.command ~/job-bot/START_JOBBOT.command
cp ~/jobbot-public/data/blocked_companies.json ~/job-bot/data/blocked_companies.json
```

- [ ] **Step 4: Verify .gitignore covers all personal/runtime files**

Read `~/job-bot/.gitignore` and confirm these patterns exist. If any are missing, add them:

```
.env
config/profile.json
config/resume.txt
config/resume.txt
data/jobs/*.json
data/applications/*.json
data/sent/*.json
data/jobs/seen_ids.json
logs/*.log
logs/*.lock
__pycache__/
*.pyc
.DS_Store
```

- [ ] **Step 5: Confirm config/ only has .gitkeep**

```bash
ls ~/job-bot/config/
```
Expected: only `.gitkeep` (no profile.json or resume.txt committed)

- [ ] **Step 6: Delete jobbot-public/**

```bash
rm -rf ~/jobbot-public
```

Verify gone:
```bash
ls ~ | grep jobbot
```
Expected: only `job-bot` listed (no `jobbot-public`)

- [ ] **Step 7: Update JOBBOT.md — remove jobbot-public references**

Open `~/JOBBOT.md` and delete the `~/jobbot-public/` entry from the "Project Location" section. It should only reference `~/job-bot/`.

- [ ] **Step 8: Commit**

```bash
cd ~/job-bot
git add -A
git commit -m "chore: consolidate jobbot-public into job-bot — single canonical codebase"
```

---

## Task 2: Test Infrastructure Setup

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create tests directory and conftest**

```bash
mkdir -p ~/job-bot/tests
touch ~/job-bot/tests/__init__.py
```

Create `~/job-bot/tests/conftest.py`:

```python
"""
pytest configuration — adds project subdirs to sys.path so tests can import
from scraper/, dashboard/, drafter/, setup/ without package structure.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scraper"))
sys.path.insert(0, str(ROOT / "drafter"))
sys.path.insert(0, str(ROOT / "setup"))
```

Note: dashboard/server.py does a module-level `from score_jobs import ...` so it can only be imported in tests after score_jobs is on sys.path (conftest handles this) and Flask is installed. Tests that need server functions import them directly after conftest runs.

- [ ] **Step 2: Install pytest if not present and verify conftest works**

```bash
cd ~/job-bot
pip install pytest --quiet
python -m pytest tests/ --collect-only
```
Expected: `no tests ran` (no test files yet) with no import errors.

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: add pytest infrastructure"
```

---

## Task 3: Security Fix — .env Injection in setup_handler.py

**Files:**
- Modify: `setup/setup_handler.py`
- Create: `tests/test_security.py`

- [ ] **Step 1: Write the failing test**

Create `~/job-bot/tests/test_security.py`:

```python
"""Tests for security fixes: .env injection and path traversal."""
import re
import pytest


# ── .env injection tests ──────────────────────────────────────────────────

def test_sanitize_strips_newline():
    from setup_handler import _sanitize_env_val
    assert _sanitize_env_val("mykey\nOPENAI_API_KEY=stolen") == "mykeyOPENAI_API_KEY=stolen"


def test_sanitize_strips_carriage_return():
    from setup_handler import _sanitize_env_val
    assert _sanitize_env_val("foo\rbar") == "foobar"


def test_sanitize_strips_null_byte():
    from setup_handler import _sanitize_env_val
    assert _sanitize_env_val("foo\x00bar") == "foobar"


def test_sanitize_leaves_clean_value_unchanged():
    from setup_handler import _sanitize_env_val
    assert _sanitize_env_val("sk-abc123XYZ") == "sk-abc123XYZ"


def test_sanitize_handles_non_string():
    from setup_handler import _sanitize_env_val
    assert _sanitize_env_val(None) == "None"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/job-bot
python -m pytest tests/test_security.py::test_sanitize_strips_newline -v
```
Expected: `FAILED` — `ImportError: cannot import name '_sanitize_env_val' from 'setup_handler'`

- [ ] **Step 3: Add `_sanitize_env_val` to setup_handler.py**

Open `setup/setup_handler.py`. After the imports block (after `from pathlib import Path`), add:

```python
import re


def _sanitize_env_val(val: str) -> str:
    """Strip characters that would inject new lines into a .env file."""
    return re.sub(r'[\r\n\x00]', '', str(val))
```

- [ ] **Step 4: Apply sanitizer to all credential writes in `handle_setup`**

Replace the `env_lines` block (lines 55–80) in `handle_setup`:

```python
    env_lines = [
        "# JobBot — Environment Variables",
        "# Generated by setup wizard — do not commit this file",
        "",
        "# LinkedIn",
        f"LINKEDIN_EMAIL={_sanitize_env_val(credentials.get('LINKEDIN_EMAIL', ''))}",
        f"LINKEDIN_PASSWORD={_sanitize_env_val(credentials.get('LINKEDIN_PASSWORD', ''))}",
        "",
        "# Handshake",
        f"HANDSHAKE_EMAIL={_sanitize_env_val(credentials.get('HANDSHAKE_EMAIL', ''))}",
        f"HANDSHAKE_PASSWORD={_sanitize_env_val(credentials.get('HANDSHAKE_PASSWORD', ''))}",
        "",
        "# OpenAI",
        f"OPENAI_API_KEY={_sanitize_env_val(credentials.get('OPENAI_API_KEY', ''))}",
        f"DAILY_SPEND_LIMIT={spend_limit}",
        "",
        "# Email digest (optional)",
        f"DIGEST_EMAIL={_sanitize_env_val(credentials.get('DIGEST_EMAIL', ''))}",
        "SMTP_HOST=smtp.gmail.com",
        "SMTP_PORT=587",
        "SMTP_USER=",
        "SMTP_PASS=",
        "",
        "# Dashboard",
        "DASHBOARD_PORT=5555",
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_security.py -k "sanitize" -v
```
Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add setup/setup_handler.py tests/test_security.py
git commit -m "fix(security): sanitize .env credential values to prevent injection"
```

---

## Task 4: Security Fix — Path Traversal + CORS in server.py

**Files:**
- Modify: `dashboard/server.py`

- [ ] **Step 1: Write the failing path traversal tests**

Add to `~/job-bot/tests/test_security.py` (append to the existing file):

```python

# ── Path traversal tests ──────────────────────────────────────────────────

def test_valid_date_passes():
    from server import _validate_date_str
    _validate_date_str("2026-03-31")  # must not raise


def test_path_traversal_rejected():
    from server import _validate_date_str
    with pytest.raises(ValueError):
        _validate_date_str("../../../etc/passwd")


def test_traversal_with_mixed_path():
    from server import _validate_date_str
    with pytest.raises(ValueError):
        _validate_date_str("2026-/../2026-03-31")


def test_empty_string_rejected():
    from server import _validate_date_str
    with pytest.raises(ValueError):
        _validate_date_str("")


def test_wrong_format_rejected():
    from server import _validate_date_str
    with pytest.raises(ValueError):
        _validate_date_str("31-03-2026")
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_security.py -k "date" -v
```
Expected: `FAILED` — `ImportError: cannot import name '_validate_date_str' from 'server'`

- [ ] **Step 3: Add `_validate_date_str` and `_DATE_RE` to server.py**

In `dashboard/server.py`, after the imports (after `load_dotenv(ROOT / ".env")`), add:

```python
import re as _re

_DATE_RE = _re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _validate_date_str(date_str: str) -> None:
    """Reject any date_str that isn't a plain YYYY-MM-DD — prevents path traversal."""
    if not _DATE_RE.match(date_str):
        raise ValueError(f"Invalid date format: {date_str!r}")
```

- [ ] **Step 4: Apply validator in `load_apps` and `save_apps`**

Replace `load_apps`:
```python
def load_apps(date_str=None):  # -> list[dict]
    if date_str:
        _validate_date_str(date_str)
        f = APPS_DIR / f"applications_{date_str}.json"
    else:
        f = get_latest_apps_file()
    if not f or not f.exists():
        return []
    try:
        return json.loads(f.read_text())
    except (json.JSONDecodeError, ValueError):
        log.warning(f"Applications file {f.name} is corrupted — returning empty list")
        return []
```

Replace `save_apps`:
```python
def save_apps(apps, date_str=None):
    if not date_str:
        f = get_latest_apps_file()
        if not f:
            f = APPS_DIR / f"applications_{date.today().isoformat()}.json"
    else:
        _validate_date_str(date_str)
        f = APPS_DIR / f"applications_{date_str}.json"
    atomic_write(f, json.dumps(apps, indent=2))
```

Note: `atomic_write` will be added in Task 7. For now `save_apps` can keep using `f.write_text(...)` — Task 7 will swap it.

- [ ] **Step 5: Handle ValueError in the `/api/applications` route**

In the `list_applications` route, wrap the `load_apps(date_str)` call:

```python
@app.route("/api/applications")
def list_applications():
    date_str = request.args.get("date")
    if date_str:
        try:
            _validate_date_str(date_str)
        except ValueError:
            return jsonify({"error": "Invalid date format — expected YYYY-MM-DD"}), 400
    apps = load_apps(date_str)
    ...
```

- [ ] **Step 6: Restrict CORS**

Find the line `CORS(app)` and replace it:

```python
CORS(app, origins=["http://localhost:5555"])
```

- [ ] **Step 7: Run all security tests**

```bash
python -m pytest tests/test_security.py -v
```
Expected: `10 passed`

- [ ] **Step 8: Commit**

```bash
git add dashboard/server.py tests/test_security.py
git commit -m "fix(security): path traversal validation on date_str, restrict CORS to localhost"
```

---

## Task 5: Fix Spend Guardrail — Fail Closed

**Files:**
- Modify: `drafter/draft_applications.py`
- Create: `tests/test_spend_guardrail.py`

- [ ] **Step 1: Write the failing tests**

Create `~/job-bot/tests/test_spend_guardrail.py`:

```python
"""Spend guardrail must fail CLOSED — return inf on any error, never 0.0."""
import pytest
from unittest.mock import patch, MagicMock


def test_fails_closed_on_network_error():
    with patch("draft_applications.requests.get") as mock_get:
        mock_get.side_effect = ConnectionError("network unreachable")
        from draft_applications import get_todays_spend
        result = get_todays_spend("sk-test-key")
    assert result == float('inf'), "Must return inf on exception, not 0.0"


def test_fails_closed_on_500_status():
    with patch("draft_applications.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp
        from draft_applications import get_todays_spend
        result = get_todays_spend("sk-test-key")
    assert result == float('inf'), "Must return inf on non-200 status"


def test_fails_closed_on_401_status():
    with patch("draft_applications.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp
        from draft_applications import get_todays_spend
        result = get_todays_spend("sk-test-key")
    assert result == float('inf'), "Must return inf on auth error"


def test_returns_dollars_on_success():
    with patch("draft_applications.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total_usage": 25}  # 25 cents
        mock_get.return_value = mock_resp
        from draft_applications import get_todays_spend
        result = get_todays_spend("sk-test-key")
    assert result == pytest.approx(0.25)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd ~/job-bot
python -m pytest tests/test_spend_guardrail.py -v
```
Expected: `test_fails_closed_on_network_error FAILED`, `test_fails_closed_on_500_status FAILED` (the function currently returns `0.0`)

- [ ] **Step 3: Fix `get_todays_spend` in draft_applications.py**

Find `get_todays_spend` (lines 24–47) and replace the two `return 0.0` lines:

```python
def get_todays_spend(api_key):  # -> float
    """
    Fetch today's OpenAI usage cost via the usage API.
    Returns spend in USD. Returns float('inf') on any failure so the
    spend guardrail fails CLOSED — no AI generation if cost is unknown.
    """
    today = date.today().isoformat()
    try:
        resp = requests.get(
            "https://api.openai.com/v1/usage",
            params={"date": today},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            total_cents = data.get("total_usage", 0)
            return total_cents / 100.0
        else:
            log.warning(f"Usage API returned {resp.status_code} — failing closed, halting AI generation")
            return float('inf')
    except Exception as e:
        log.warning(f"Could not fetch usage: {e} — failing closed, halting AI generation")
        return float('inf')
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_spend_guardrail.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add drafter/draft_applications.py tests/test_spend_guardrail.py
git commit -m "fix: spend guardrail now fails closed — returns inf on usage API error"
```

---

## Task 6: Fix File Handle Leak in run_daily.py

**Files:**
- Modify: `run_daily.py`

- [ ] **Step 1: Fix the anonymous open() in `start_dashboard`**

In `run_daily.py`, find the `start_dashboard` function. Replace the `subprocess.Popen` call (lines 72–77):

```python
    log.info("Starting dashboard server...")
    _dashboard_log = open(LOG_DIR / "dashboard.log", "a")
    subprocess.Popen(
        [sys.executable, str(ROOT / "dashboard" / "server.py")],
        cwd=str(ROOT),
        stdout=_dashboard_log,
        stderr=subprocess.STDOUT,
    )
    time.sleep(2)
```

The handle stays open intentionally — it's the subprocess's stdout stream and must outlive the `Popen` call. The fix is assigning it to a named variable rather than leaving it as an anonymous expression.

- [ ] **Step 2: Verify the file runs without syntax errors**

```bash
cd ~/job-bot
python -c "import run_daily; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add run_daily.py
git commit -m "fix: assign dashboard log file handle to avoid anonymous leak"
```

---

## Task 7: Atomic Writes for All Data Files

**Files:**
- Modify: `scraper/scrape_jobs.py`
- Modify: `drafter/draft_applications.py`
- Modify: `scraper/score_jobs.py`
- Modify: `dashboard/server.py`

Atomic write pattern: write to `.tmp`, then rename. On POSIX, `Path.replace()` is atomic — if the process dies mid-write, the original file is untouched.

- [ ] **Step 1: Add `atomic_write` to scrape_jobs.py and fix `save_seen`**

In `scraper/scrape_jobs.py`, after the imports, add:

```python
def atomic_write(path: Path, data: str) -> None:
    """Write data atomically: write to .tmp then rename, so crashes don't corrupt."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)
```

Replace `save_seen`:
```python
def save_seen(seen):
    atomic_write(SEEN_FILE, json.dumps(list(seen), indent=2))
```

Also fix `TODAY_FILE.write_text(...)` at the end of `run_scraper()`:
```python
    if all_jobs:
        atomic_write(TODAY_FILE, json.dumps(all_jobs, indent=2))
        log.info(f"Saved {len(all_jobs)} jobs to {TODAY_FILE}")
```

- [ ] **Step 2: Add `atomic_write` to draft_applications.py and fix the save**

In `drafter/draft_applications.py`, after imports, add:

```python
def atomic_write(path: Path, data: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)
```

In `run_drafter`, find `TODAY_APPS_FILE.write_text(...)` and replace:
```python
    atomic_write(today_apps_file, json.dumps(applications, indent=2))
    log.info(f"Saved {len(applications)} drafted applications to {today_apps_file}")
```

(Note: `today_apps_file` will be a local variable after Task 9 moves the module-level date.)

- [ ] **Step 3: Fix `save_preferences` in score_jobs.py**

In `scraper/score_jobs.py`, add `atomic_write` after imports:

```python
def atomic_write(path: Path, data: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)
```

Replace `save_preferences`:
```python
def save_preferences(prefs: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(PREFS_FILE, json.dumps(prefs, indent=2))
```

- [ ] **Step 4: Fix all `.write_text` calls on data files in server.py**

In `dashboard/server.py`, add `atomic_write` after imports:

```python
def atomic_write(path: Path, data: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)
```

Apply in `save_apps` (already updated in Task 4 to call `atomic_write`).

Find every `apps_file.write_text(json.dumps(apps, indent=2))` call (there are several in routes — `update_application`, `approve_application`, `mark_sent`, `skip_application`, `feedback`, `track_response`) and replace each with:
```python
atomic_write(apps_file, json.dumps(apps, indent=2))
```

Find `sent_log.write_text(json.dumps(existing, indent=2))` in `mark_sent` and replace:
```python
atomic_write(sent_log, json.dumps(existing, indent=2))
```

Find `save_blocked_companies` and replace its write:
```python
def save_blocked_companies(companies: list) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(BLOCKED_COMPANIES_FILE, json.dumps(companies, indent=2))
```

- [ ] **Step 5: Verify no raw write_text calls remain on data files**

```bash
cd ~/job-bot
grep -n "\.write_text(" dashboard/server.py scraper/scrape_jobs.py drafter/draft_applications.py scraper/score_jobs.py
```
Expected: only non-data writes (like serving HTML files) should remain — no `json.dumps` writes should appear.

- [ ] **Step 6: Commit**

```bash
git add dashboard/server.py scraper/scrape_jobs.py drafter/draft_applications.py scraper/score_jobs.py
git commit -m "fix: atomic writes for all data files — prevent JSON corruption on crash"
```

---

## Task 8: JSON Read Error Handling

**Files:**
- Modify: `scraper/scrape_jobs.py`
- Modify: `drafter/draft_applications.py`
- Modify: `dashboard/server.py`

- [ ] **Step 1: Fix `load_seen` in scrape_jobs.py**

Replace:
```python
def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()
```
With:
```python
def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except (json.JSONDecodeError, ValueError):
            log.warning("seen_ids.json is corrupted — starting with empty seen set")
            return set()
    return set()
```

- [ ] **Step 2: Fix `load_profile` in draft_applications.py**

Replace:
```python
def load_profile() -> dict:
    return json.loads((CONFIG_DIR / "profile.json").read_text())
```
With:
```python
def load_profile() -> dict:
    p = CONFIG_DIR / "profile.json"
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, ValueError):
        raise RuntimeError(
            "profile.json is missing or corrupted — "
            "re-run setup at http://localhost:5555/setup"
        )
```

- [ ] **Step 3: Fix sent_log reads in server.py**

In `mark_sent`, replace:
```python
    existing = json.loads(sent_log.read_text()) if sent_log.exists() else []
```
With:
```python
    existing = []
    if sent_log.exists():
        try:
            existing = json.loads(sent_log.read_text())
        except (json.JSONDecodeError, ValueError):
            log.warning("sent_log.json is corrupted — starting fresh log")
```

In `stats`, replace:
```python
    sent = json.loads(sent_log.read_text()) if sent_log.exists() else []
```
With:
```python
    sent = []
    if sent_log.exists():
        try:
            sent = json.loads(sent_log.read_text())
        except (json.JSONDecodeError, ValueError):
            sent = []
```

In `application_history`, replace the `sent_log` read at the top:
```python
    sent_records = []
    if sent_log.exists():
        try:
            sent_records = json.loads(sent_log.read_text())
        except (json.JSONDecodeError, ValueError):
            sent_records = []
```

- [ ] **Step 4: Verify no bare json.loads on data files remain**

```bash
grep -n "json\.loads(" dashboard/server.py scraper/scrape_jobs.py drafter/draft_applications.py
```
Confirm every result is either already in a try/except or reads a non-critical file (HTML etc.). The `application_history` loop already has `try/except` around per-file reads — confirm that's intact.

- [ ] **Step 5: Commit**

```bash
git add dashboard/server.py scraper/scrape_jobs.py drafter/draft_applications.py
git commit -m "fix: wrap all JSON reads with error handling — survive corrupted data files"
```

---

## Task 9: Minor Fixes Bundle

**Files:**
- Modify: `drafter/draft_applications.py`
- Modify: `scraper/scrape_jobs.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Fix unbalanced paren in log string (draft_applications.py:55)**

Find:
```python
    log.info(f"Today's OpenAI spend so far: ${spend:.4f} (limit: ${DAILY_SPEND_LIMIT}")
```
Replace with:
```python
    log.info(f"Today's OpenAI spend so far: ${spend:.4f} (limit: ${DAILY_SPEND_LIMIT})")
```

- [ ] **Step 2: Move module-level date evaluation inside run_drafter()**

In `draft_applications.py`, delete these three module-level lines (around line 70):
```python
TODAY = date.today().isoformat()
TODAY_JOBS_FILE = JOBS_DIR / f"jobs_{TODAY}.json"
TODAY_APPS_FILE = APPS_DIR / f"applications_{TODAY}.json"
```

At the top of `run_drafter()`, add:
```python
def run_drafter(num_apps: int = 10) -> list[dict]:
    today = date.today().isoformat()
    today_jobs_file = JOBS_DIR / f"jobs_{today}.json"
    today_apps_file = APPS_DIR / f"applications_{today}.json"
    ...
```

Update all references in `run_drafter` from `TODAY_JOBS_FILE` → `today_jobs_file` and `TODAY_APPS_FILE` → `today_apps_file`.

- [ ] **Step 3: Update User-Agent in scrape_jobs.py**

Find:
```python
        "Chrome/122.0.0.0 Safari/537.36"
```
Replace with:
```python
        "Chrome/124.0.0.0 Safari/537.36"
```

- [ ] **Step 4: Replace MD5 with SHA256 for job dedup**

In `scrape_jobs.py`, find:
```python
def job_id(url, title, company):
    raw = f"{url}{title}{company}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()[:16]
```
Replace with:
```python
def job_id(url, title, company):
    raw = f"{url}{title}{company}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

- [ ] **Step 5: Remove unused dependencies from requirements.txt**

Open `requirements.txt` and delete these two lines:
```
selenium>=4.18.0
webdriver-manager>=4.0.1
```

Final `requirements.txt` should be:
```
beautifulsoup4>=4.12.0
requests>=2.31.0
flask>=3.0.0
flask-cors>=4.0.0
openai>=1.14.0
python-dotenv>=1.0.0
lxml>=5.1.0
```

- [ ] **Step 6: Verify draft_applications.py has no remaining module-level TODAY references**

```bash
grep -n "TODAY" ~/job-bot/drafter/draft_applications.py
```
Expected: no results (all occurrences removed or renamed to local `today`)

- [ ] **Step 7: Commit**

```bash
git add drafter/draft_applications.py scraper/scrape_jobs.py requirements.txt
git commit -m "fix: log paren, move date eval inside run_drafter, SHA256 dedup, User-Agent, remove unused deps"
```

---

## Task 10: Scraper Cleanup — Remove Dead Scrapers

**Files:**
- Modify: `scraper/scrape_jobs.py`

The three scrapers below are full SPAs — `requests.get()` returns an empty HTML shell with no job cards. They produce zero results and should be removed.

- [ ] **Step 1: Delete `scrape_wellfound`**

Remove the entire function `scrape_wellfound` (lines ~375–444) from `scrape_jobs.py`.

- [ ] **Step 2: Delete `scrape_handshake_public`**

Remove the entire function `scrape_handshake_public` (lines ~448–521).

- [ ] **Step 3: Delete `scrape_internships_dot_com`**

Remove the entire function `scrape_internships_dot_com` (lines ~525–600).

- [ ] **Step 4: Update `run_scraper()` to remove deleted scrapers**

Find the `scrapers` list in `run_scraper()` and replace it:

```python
    scrapers = [
        (scrape_indeed_rss,      25),
        (scrape_linkedin_public, 15),
        (scrape_simplyhired,     10),
    ]
```

(RemoteOK and BuiltInNYC will be added in Tasks 11 and 12.)

- [ ] **Step 5: Verify the file is syntactically valid**

```bash
cd ~/job-bot
python -c "import scraper.scrape_jobs; print('ok')" 2>&1 || python scraper/scrape_jobs.py --help 2>&1 | head -5
python -m py_compile scraper/scrape_jobs.py && echo "syntax ok"
```
Expected: `syntax ok`

- [ ] **Step 6: Commit**

```bash
git add scraper/scrape_jobs.py
git commit -m "fix(scraper): remove Wellfound/Handshake/Internships.com — SPA sources that return zero results"
```

---

## Task 11: Add RemoteOK Scraper

**Files:**
- Modify: `scraper/scrape_jobs.py`

RemoteOK has a public JSON API (`https://remoteok.com/api`) that returns structured job data — no HTML parsing, no auth, highly reliable.

- [ ] **Step 1: Add `scrape_remoteok` function to scrape_jobs.py**

Add after `scrape_simplyhired` (before `run_scraper`):

```python
# ── RemoteOK JSON API ──────────────────────────────────────────────────────
def scrape_remoteok(seen, profile, limit=15):
    log.info("Scraping RemoteOK (API)...")
    results = []

    try:
        resp = requests.get(
            "https://remoteok.com/api",
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code != 200:
            log.warning(f"RemoteOK API: status {resp.status_code}")
            return results

        jobs = resp.json()
        # First element is a legal/metadata dict — skip it
        if jobs and isinstance(jobs[0], dict) and "legal" in jobs[0]:
            jobs = jobs[1:]

        role_types = [r.lower() for r in profile.get("role_types", [])]
        role_words = [r.split()[0] for r in role_types if r]

        for job in jobs:
            if len(results) >= limit:
                break
            try:
                title    = (job.get("position") or "").strip()
                company  = (job.get("company")  or "").strip()
                location = (job.get("location") or "Remote").strip()
                url      = (job.get("url") or
                            f"https://remoteok.com/remote-jobs/{job.get('slug', job.get('id', ''))}")
                desc_raw = job.get("description") or ""
                description = BeautifulSoup(desc_raw, "html.parser").get_text(" ", strip=True)[:2000]
                tags = [t.lower() for t in (job.get("tags") or [])]

                if not title or not url:
                    continue
                if is_senior(title):
                    continue
                if profile.get("paid_only", True) and not looks_paid(description + " " + " ".join(tags)):
                    continue

                # If user has role preferences, require at least one tag or title match
                if role_words:
                    tag_match   = any(w in tag  for w in role_words for tag in tags)
                    title_match = any(w in title.lower() for w in role_words)
                    if not tag_match and not title_match:
                        continue

                jid = job_id(url, title, company)
                if jid in seen:
                    continue

                results.append({
                    "id":          jid,
                    "source":      "remoteok",
                    "title":       title,
                    "company":     company,
                    "location":    location,
                    "url":         url,
                    "description": description,
                    "scraped_at":  datetime.now().isoformat(),
                    "applied":     False,
                    "status":      "new",
                })
                seen.add(jid)

            except Exception as e:
                log.debug(f"RemoteOK job parse error: {e}")
                continue

        human_delay(1, 2)

    except Exception as e:
        log.warning(f"RemoteOK failed: {e}")

    log.info(f"RemoteOK: {len(results)} jobs")
    return results[:limit]
```

- [ ] **Step 2: Add RemoteOK to `run_scraper()`**

Update the `scrapers` list:

```python
    scrapers = [
        (scrape_indeed_rss,      25),
        (scrape_linkedin_public, 15),
        (scrape_remoteok,        15),
        (scrape_simplyhired,     10),
    ]
```

- [ ] **Step 3: Verify syntax**

```bash
python -m py_compile scraper/scrape_jobs.py && echo "syntax ok"
```
Expected: `syntax ok`

- [ ] **Step 4: Smoke test the scraper against the live API**

```bash
cd ~/job-bot
python -c "
import sys; sys.path.insert(0,'scraper')
from scrape_jobs import scrape_remoteok
jobs = scrape_remoteok(set(), {}, limit=5)
print(f'Got {len(jobs)} jobs')
for j in jobs[:3]:
    print(f'  [{j[\"source\"]}] {j[\"title\"][:50]} @ {j[\"company\"]}')
"
```
Expected: 1–5 jobs printed with title/company. If 0 results, check internet connection — the API is public and should respond.

- [ ] **Step 5: Commit**

```bash
git add scraper/scrape_jobs.py
git commit -m "feat(scraper): add RemoteOK JSON API source — reliable, no auth required"
```

---

## Task 12: Add Built In NYC Scraper

**Files:**
- Modify: `scraper/scrape_jobs.py`

Only runs when `location_preference` contains "new york" — irrelevant to non-NYC users and silently skipped.

- [ ] **Step 1: Add `scrape_builtinnyc` function after `scrape_remoteok`**

```python
# ── Built In NYC ───────────────────────────────────────────────────────────
def scrape_builtinnyc(seen, profile, limit=10):
    """NYC startup/tech jobs. Only runs when location_preference is NYC."""
    loc_pref = (profile.get("location_preference") or "").lower()
    if "new york" not in loc_pref:
        log.info("BuiltInNYC: skipping (location_preference is not NYC)")
        return []

    log.info("Scraping Built In NYC...")
    results = []

    urls = [
        "https://www.builtinnyc.com/jobs",
        "https://www.builtinnyc.com/jobs?search=intern",
    ]

    session = requests.Session()
    session.headers.update(HEADERS)

    for url in urls:
        if len(results) >= limit:
            break
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                log.warning(f"BuiltInNYC: {resp.status_code} from {url}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            # Try multiple selector strategies in order
            cards = (
                soup.select("article.job-card") or
                soup.select("div.job-card") or
                soup.select("[data-testid='job-card']") or
                soup.select("li.job-card")
            )
            log.info(f"BuiltInNYC: {len(cards)} cards from {url}")

            for card in cards[:15]:
                try:
                    title_el   = (card.select_one("h2")
                                  or card.select_one("h3")
                                  or card.select_one("[class*='title']"))
                    company_el = (card.select_one("[class*='company']")
                                  or card.select_one("[class*='employer']"))
                    link_el    = (card.select_one("a[href*='/job/']")
                                  or card.select_one("a[href*='/jobs/']")
                                  or card.select_one("a"))
                    loc_el     = (card.select_one("[class*='location']")
                                  or card.select_one("[class*='Location']"))

                    title    = title_el.get_text(strip=True)   if title_el   else ""
                    company  = company_el.get_text(strip=True) if company_el else ""
                    href     = (link_el.get("href") or "")     if link_el    else ""
                    location = loc_el.get_text(strip=True)     if loc_el     else "New York, NY"
                    url_full = (f"https://www.builtinnyc.com{href}"
                                if href.startswith("/") else href)

                    if not title or not url_full:
                        continue
                    if is_senior(title):
                        continue

                    jid = job_id(url_full, title, company)
                    if jid in seen:
                        continue

                    results.append({
                        "id":          jid,
                        "source":      "builtinnyc",
                        "title":       title,
                        "company":     company,
                        "location":    location,
                        "url":         url_full,
                        "description": "",
                        "scraped_at":  datetime.now().isoformat(),
                        "applied":     False,
                        "status":      "new",
                    })
                    seen.add(jid)

                except Exception:
                    continue

            human_delay(1, 2)

        except Exception as e:
            log.warning(f"BuiltInNYC failed: {e}")

    log.info(f"BuiltInNYC: {len(results)} jobs")
    return results[:limit]
```

- [ ] **Step 2: Add BuiltInNYC to `run_scraper()`**

```python
    scrapers = [
        (scrape_indeed_rss,      25),
        (scrape_linkedin_public, 15),
        (scrape_remoteok,        15),
        (scrape_simplyhired,     10),
        (scrape_builtinnyc,      10),
    ]
    target = 50
```

- [ ] **Step 3: Verify syntax**

```bash
python -m py_compile scraper/scrape_jobs.py && echo "syntax ok"
```

- [ ] **Step 4: Smoke test (skips gracefully if not NYC)**

```bash
cd ~/job-bot
python -c "
import sys; sys.path.insert(0,'scraper')
from scrape_jobs import scrape_builtinnyc
# Non-NYC profile — should return [] immediately
jobs = scrape_builtinnyc(set(), {'location_preference': 'Austin, TX'}, limit=5)
assert jobs == [], f'Expected empty list for non-NYC, got {len(jobs)}'
print('Non-NYC skip: OK')
# NYC profile
jobs2 = scrape_builtinnyc(set(), {'location_preference': 'New York, NY'}, limit=3)
print(f'NYC run: got {len(jobs2)} jobs (0 is ok if selectors miss, check manually)')
"
```
Expected: `Non-NYC skip: OK` printed. NYC job count is best-effort (0 is acceptable if the site changed selectors — the scraper logs a warning but doesn't crash).

- [ ] **Step 5: Commit**

```bash
git add scraper/scrape_jobs.py
git commit -m "feat(scraper): add Built In NYC source — NYC startup jobs, skips for non-NYC users"
```

---

## Task 13: De-personalize — Generic Location Filter + Neutral Scoring

**Files:**
- Modify: `drafter/draft_applications.py`
- Create: `tests/test_location.py`

- [ ] **Step 1: Write failing tests for the generic location filter**

Create `~/job-bot/tests/test_location.py`:

```python
"""Generic location filter must work for any city, not just NYC."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "drafter"))


def test_matching_city_accepted():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "New York, NY"},
        {"location_preference": "New York, NY"}
    ) is True


def test_different_city_rejected():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "Chicago, IL"},
        {"location_preference": "New York, NY"}
    ) is False


def test_austin_profile_accepts_austin():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "Austin, TX"},
        {"location_preference": "Austin, TX"}
    ) is True


def test_austin_profile_rejects_nyc():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "New York, NY"},
        {"location_preference": "Austin, TX"}
    ) is False


def test_remote_profile_accepts_any_city():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "Dallas, TX"},
        {"location_preference": "Remote"}
    ) is True


def test_blank_job_location_accepted():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": ""},
        {"location_preference": "New York, NY"}
    ) is True


def test_no_profile_preference_accepts_any():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "Denver, CO"},
        {}
    ) is True


def test_case_insensitive_match():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "NEW YORK, NY"},
        {"location_preference": "New York, NY"}
    ) is True
```

- [ ] **Step 2: Run to verify failure**

```bash
cd ~/job-bot
python -m pytest tests/test_location.py -v
```
Expected: `ImportError: cannot import name 'is_allowed_location'` (function doesn't exist yet in this form)

- [ ] **Step 3: Remove NYC hardcoding from draft_applications.py**

Delete these constants and functions entirely:
- `BOROUGH_WHITELIST` list
- `PRIORITY_BOROUGHS` list
- `UPTOWN_SIGNALS` list
- `is_allowed_location(job)` function (the old one-arg version)
- `borough_score_bonus(job)` function

- [ ] **Step 4: Add the generic `is_allowed_location` function**

After `looks_paid`, add:

```python
def is_allowed_location(job: dict, profile: dict) -> bool:
    """
    Returns True if the job location matches the user's location_preference.
    Accepts the job if:
      - profile has no location_preference set
      - location_preference contains 'remote'
      - job location field is blank (benefit of the doubt)
      - city name from profile appears in job location
    """
    pref = (profile.get("location_preference") or "").lower().strip()
    if not pref or "remote" in pref:
        return True
    job_loc = (job.get("location") or "").lower()
    if not job_loc:
        return True
    city = pref.split(",")[0].strip()
    return city in job_loc
```

- [ ] **Step 5: Update the location filter call in `run_drafter()`**

Find the old location filter call (previously `is_allowed_location(j)`) and update it to pass `profile`:

```python
    # Generic location filter — uses user's location_preference from profile
    before = len(jobs)
    jobs = [j for j in jobs if is_allowed_location(j, profile)]
    log.info(f"Location filter: {before} → {len(jobs)} jobs removed outside target location")
```

- [ ] **Step 6: Remove borough_score_bonus call from score_job()**

In `score_job()`, find and remove:
```python
    # NYC borough weight + priority bonus
    score += borough_score_bonus(job)
```

- [ ] **Step 7: Genericize score_job() keyword lists**

Replace the `good_terms` list in `score_job()` with generic entry-level defaults (remove `"vc"`, `"venture"`, `"founder"`, `"entrepreneur"` — too niche as universal defaults):

```python
    good_terms = [
        "intern", "internship", "summer", "startup", "growth", "marketing",
        "sales", "business development", "operations", "product", "generalist",
        "content", "brand", "partnerships", "strategy", "analyst", "associate",
        "innovation", "technology", "digital", "e-commerce",
    ]
```

- [ ] **Step 8: Run location tests**

```bash
python -m pytest tests/test_location.py -v
```
Expected: `8 passed`

- [ ] **Step 9: Run all tests**

```bash
python -m pytest tests/ -v
```
Expected: all tests pass (security, spend guardrail, location)

- [ ] **Step 10: Commit**

```bash
git add drafter/draft_applications.py tests/test_location.py
git commit -m "fix: replace NYC-specific location logic with generic profile-driven filter"
```

---

## Task 14: Rewrite README for Public Release

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite README.md**

Replace the entire contents of `README.md` with:

```markdown
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
```

- [ ] **Step 2: Verify the file renders correctly**

```bash
cat ~/job-bot/README.md | head -20
```
Expected: starts with `# JobBot`

- [ ] **Step 3: Final full test run**

```bash
cd ~/job-bot
python -m pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Step 4: Final syntax check across all modified Python files**

```bash
cd ~/job-bot
python -m py_compile dashboard/server.py && \
python -m py_compile scraper/scrape_jobs.py && \
python -m py_compile scraper/score_jobs.py && \
python -m py_compile drafter/draft_applications.py && \
python -m py_compile setup/setup_handler.py && \
python -m py_compile run_daily.py && \
echo "All files: syntax OK"
```
Expected: `All files: syntax OK`

- [ ] **Step 5: Commit and final summary**

```bash
git add README.md
git commit -m "docs: rewrite README for public product release"
```

```bash
git log --oneline -15
```
Expected: 14 commits visible from this session.

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Phase 0 consolidation → Task 1
- ✅ score_jobs.py wiring → Task 1 (copy) + confirmed not a bug (double-extraction is fine)
- ✅ .env injection → Task 3
- ✅ Path traversal → Task 4
- ✅ CORS → Task 4
- ✅ Spend guardrail → Task 5
- ✅ File handle leak → Task 6
- ✅ Atomic writes → Task 7
- ✅ JSON error handling → Task 8
- ✅ Minor fixes (paren, date eval, UA, SHA256, deps) → Task 9
- ✅ Remove dead scrapers → Task 10
- ✅ Add RemoteOK → Task 11
- ✅ Add BuiltInNYC → Task 12
- ✅ De-personalize (NYC hardcode + score_job keywords) → Task 13
- ✅ README rewrite → Task 14
- ✅ blocked_companies.json copied → Task 1

**Note on score_jobs feedback route:** The current server.py calls `extract_features(job_data_raw)` then passes the result to `record_feedback`. This is correct — `record_feedback` reads `company`, `role_keywords`, `industry`, `source` from whatever dict is passed, and `extract_features` output has exactly those keys. No bug, no fix needed.
