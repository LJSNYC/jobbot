#!/usr/bin/env python3
"""
JobBot — Local dashboard server.
Serves the review UI at http://localhost:5555
Also serves the setup wizard at http://localhost:5555/setup
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import webbrowser
from datetime import date, datetime
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))
from score_jobs import extract_features, record_feedback, score_job, load_preferences

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
APPS_DIR = DATA_DIR / "applications"
SENT_DIR = DATA_DIR / "sent"
SENT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = ROOT / "logs"
SETUP_DIR = Path(__file__).parent.parent / "setup"
BLOCKED_COMPANIES_FILE = DATA_DIR / "blocked_companies.json"

load_dotenv(ROOT / ".env")

import re as _re

_DATE_RE = _re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _validate_date_str(date_str: str) -> None:
    """Reject any date_str that isn't plain YYYY-MM-DD — prevents path traversal."""
    if not _DATE_RE.match(date_str):
        raise ValueError(f"Invalid date format: {date_str!r}")


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dashboard")


def atomic_write(path: Path, data: str) -> None:
    """Write data atomically: write to .tmp then rename, so crashes don't corrupt."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)

app = Flask(__name__)
CORS(app, origins=["http://localhost:5555"])


# ── Helpers ────────────────────────────────────────────────────────────────
def get_latest_apps_file():  # -> Path | None
    files = sorted(APPS_DIR.glob("applications_*.json"), reverse=True)
    return files[0] if files else None


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


def save_apps(apps, date_str=None):
    if not date_str:
        f = get_latest_apps_file()
        if not f:
            f = APPS_DIR / f"applications_{date.today().isoformat()}.json"
    else:
        _validate_date_str(date_str)
        f = APPS_DIR / f"applications_{date_str}.json"
    atomic_write(f, json.dumps(apps, indent=2))


def find_app(apps, app_id):  # -> tuple[int, dict | None]
    for i, a in enumerate(apps):
        if a["id"] == app_id:
            return i, a
    return -1, None


def find_app_any_date(app_id):  # -> tuple[Path, int, dict | None]
    """Search all applications files for an app_id. Returns (file_path, index, app)."""
    for apps_file in sorted(APPS_DIR.glob("applications_*.json"), reverse=True):
        try:
            apps = json.loads(apps_file.read_text())
            idx, a = find_app(apps, app_id)
            if a is not None:
                return apps_file, idx, apps, a
        except Exception:
            continue
    return None, -1, [], None


# ── Setup wizard routes ────────────────────────────────────────────────────

@app.route("/setup")
def setup_wizard():
    """Serve the onboarding wizard HTML."""
    html_file = SETUP_DIR / "onboarding.html"
    if html_file.exists():
        return html_file.read_text()
    return "<h1>Setup wizard not found.</h1><p>Make sure setup/onboarding.html exists.</p>", 404


@app.route("/api/setup", methods=["POST"])
def handle_setup():
    """Receive form data from the onboarding wizard, write config files."""
    try:
        # Import here so the server can start even before setup files exist
        import sys as _sys
        _sys.path.insert(0, str(SETUP_DIR))
        from setup_handler import handle_setup as _do_setup

        data = request.json or {}
        result = _do_setup(data, ROOT)
        return jsonify(result)
    except Exception as e:
        log.error(f"Setup failed: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── API Routes ─────────────────────────────────────────────────────────────

@app.route("/api/applications")
def list_applications():
    date_str = request.args.get("date")
    if date_str:
        try:
            _validate_date_str(date_str)
        except ValueError:
            return jsonify({"error": "Invalid date format — expected YYYY-MM-DD"}), 400
    apps = load_apps(date_str)
    prefs = load_preferences()
    summary = []
    for a in apps:
        job = a.get("job", {})
        pref_score = a.get("preference_score", score_job(job, prefs))
        summary.append({
            "id": a["id"],
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "source": job.get("source", ""),
            "score": a.get("score", 0),
            "preference_score": pref_score,
            "fit_summary": a.get("fit_summary", ""),
            "status": a.get("status", "pending_review"),
            "url": job.get("url", ""),
            "apply_url": a.get("apply_info", {}).get("apply_url", ""),
            "drafted_at": a.get("drafted_at", ""),
            "sent_at": a.get("sent_at"),
            "response_status": a.get("response_status", "no_response"),
        })
    summary.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(summary)


@app.route("/api/application/<app_id>")
def get_application(app_id):
    _, _, _, a = find_app_any_date(app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404
    prefs = load_preferences()
    a["preference_score"] = a.get("preference_score", score_job(a.get("job", {}), prefs))
    return jsonify(a)


@app.route("/api/application/<app_id>", methods=["PATCH"])
def update_application(app_id):
    apps_file, idx, apps, a = find_app_any_date(app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404

    data = request.json
    allowed = ["cover_letter", "about_me", "notes", "status"]
    for k in allowed:
        if k in data:
            apps[idx][k] = data[k]

    atomic_write(apps_file, json.dumps(apps, indent=2))
    return jsonify({"ok": True, "updated": app_id})


@app.route("/api/application/<app_id>/approve", methods=["POST"])
def approve_application(app_id):
    """Mark as approved and open apply URL in browser."""
    apps_file, idx, apps, a = find_app_any_date(app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404

    apps[idx]["status"] = "approved"
    atomic_write(apps_file, json.dumps(apps, indent=2))

    apply_url = a.get("apply_info", {}).get("apply_url", "")
    return jsonify({
        "ok": True,
        "apply_url": apply_url,
        "prefill": a.get("apply_info", {}).get("prefill", {}),
        "cover_letter": a.get("cover_letter", ""),
        "about_me": a.get("about_me", "")
    })


@app.route("/api/application/<app_id>/mark_sent", methods=["POST"])
def mark_sent(app_id):
    apps_file, idx, apps, a = find_app_any_date(app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404

    apps[idx]["status"] = "sent"
    apps[idx]["sent_at"] = datetime.now().isoformat()
    atomic_write(apps_file, json.dumps(apps, indent=2))

    sent_log = SENT_DIR / "sent_log.json"
    existing = json.loads(sent_log.read_text()) if sent_log.exists() else []
    existing.append({
        "id": app_id,
        "title": a.get("job", {}).get("title", ""),
        "company": a.get("job", {}).get("company", ""),
        "url": a.get("job", {}).get("url", ""),
        "sent_at": apps[idx]["sent_at"]
    })
    atomic_write(sent_log, json.dumps(existing, indent=2))

    return jsonify({"ok": True, "sent_at": apps[idx]["sent_at"]})


@app.route("/api/application/<app_id>/skip", methods=["POST"])
def skip_application(app_id):
    apps_file, idx, apps, a = find_app_any_date(app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404
    apps[idx]["status"] = "skipped"
    atomic_write(apps_file, json.dumps(apps, indent=2))
    return jsonify({"ok": True})


@app.route("/api/feedback", methods=["POST"])
def feedback():
    """
    Record approve/skip feedback for preference learning.
    Expects JSON: { job_id, action: "approve"|"skip", job_data: {company, title, description, source} }
    Extracts features, updates weights in preferences.json, and marks the job status.
    """
    data = request.json or {}
    job_id = data.get("job_id")
    action = data.get("action")
    job_data_raw = data.get("job_data", {})

    if action not in ("approve", "skip"):
        return jsonify({"ok": False, "error": "action must be 'approve' or 'skip'"}), 400

    # Extract features from the raw job data
    features = extract_features(job_data_raw)

    # Record feedback and update weights
    prefs = record_feedback(action, features)

    # Also update the application status in the file
    if job_id:
        apps_file, idx, apps, a = find_app_any_date(job_id)
        if a is not None:
            new_status = "approved" if action == "approve" else "skipped"
            apps[idx]["status"] = new_status
            apps[idx]["preference_score"] = score_job(a.get("job", {}), prefs)
            atomic_write(apps_file, json.dumps(apps, indent=2))

    return jsonify({"ok": True, "action": action, "weights": prefs["weights"]})


@app.route("/api/stats")
def stats():
    sent_log = SENT_DIR / "sent_log.json"
    sent = json.loads(sent_log.read_text()) if sent_log.exists() else []

    apps_files = sorted(APPS_DIR.glob("applications_*.json"), reverse=True)
    today_apps = load_apps()

    pending  = len([a for a in today_apps if a["status"] == "pending_review"])
    approved = len([a for a in today_apps if a["status"] == "approved"])  # opened but not sent
    skipped  = len([a for a in today_apps if a["status"] == "skipped"])

    # Count responses across all applications files
    total_responses = 0
    for apps_file in apps_files:
        try:
            file_apps = json.loads(apps_file.read_text())
            total_responses += len([a for a in file_apps
                                    if a.get("response_status") in ("got_response", "interview")])
        except Exception:
            pass

    return jsonify({
        "total_sent": len(sent),       # only jobs explicitly marked sent
        "today_pending": pending,
        "today_approved": approved,
        "today_skipped": skipped,
        "days_active": len(apps_files),
        "recent_sent": sent[-5:][::-1],
        "total_responses": total_responses,
    })


@app.route("/api/dates")
def available_dates():
    files = sorted(APPS_DIR.glob("applications_*.json"), reverse=True)
    dates = [f.stem.replace("applications_", "") for f in files]
    return jsonify(dates)


@app.route("/api/history")
def application_history():
    """
    Return all applications the user has ever marked as sent, across all dates.
    Reads sent_log.json for sent records, cross-references applications files
    for cover letters. Skipped jobs are excluded.
    """
    sent_log = SENT_DIR / "sent_log.json"
    sent_records = json.loads(sent_log.read_text()) if sent_log.exists() else []

    # Build a quick lookup: app_id -> date string
    # Also scan all applications files for cover letters
    cover_letters = {}
    for apps_file in sorted(APPS_DIR.glob("applications_*.json"), reverse=True):
        date_str = apps_file.stem.replace("applications_", "")
        try:
            apps = json.loads(apps_file.read_text())
            for a in apps:
                if a.get("status") == "sent":  # only truly sent jobs
                    cover_letters[a["id"]] = {
                        "cover_letter": a.get("cover_letter", ""),
                        "about_me": a.get("about_me", ""),
                        "apply_url": a.get("apply_info", {}).get("apply_url", ""),
                        "fit_summary": a.get("fit_summary", ""),
                        "date": date_str,
                        "title": a.get("job", {}).get("title", ""),
                        "company": a.get("job", {}).get("company", ""),
                        "url": a.get("job", {}).get("url", ""),
                        "source": a.get("job", {}).get("source", ""),
                        "response_status": a.get("response_status", "no_response"),
                    }
        except Exception:
            continue

    # Merge sent_log with cover letter data
    history = []
    seen_ids = set()
    for record in reversed(sent_records):  # newest first after reversing
        rid = record["id"]
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        entry = {
            "id": rid,
            "title": record.get("title", ""),
            "company": record.get("company", ""),
            "url": record.get("url", ""),
            "sent_at": record.get("sent_at", ""),
            "cover_letter": "",
            "about_me": "",
            "apply_url": "",
            "fit_summary": "",
            "source": "",
            "date": record.get("sent_at", "")[:10] if record.get("sent_at") else "",
            "response_status": "no_response",
        }
        if rid in cover_letters:
            entry.update(cover_letters[rid])
        history.append(entry)

    history.sort(key=lambda x: x.get("sent_at", "") or x.get("date", ""), reverse=True)
    return jsonify(history)


# ── PDF Resume Parser ──────────────────────────────────────────────────────
@app.route("/api/parse-resume", methods=["POST"])
def parse_resume():
    """Accept a PDF/DOCX/TXT upload and return extracted plain text (max 4k chars)."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400

    f = request.files["file"]
    filename = f.filename.lower()

    try:
        if filename.endswith(".txt"):
            text = f.read().decode("utf-8", errors="ignore")

        elif filename.endswith(".pdf"):
            import io
            pdf_bytes = f.read()
            text = ""
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(pdf_bytes))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except ImportError:
                try:
                    from pdfminer.high_level import extract_text as pdfminer_extract
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(pdf_bytes)
                        tmp_path = tmp.name
                    text = pdfminer_extract(tmp_path)
                    os.unlink(tmp_path)
                except ImportError:
                    return jsonify({"ok": False, "error": "PDF parsing not available. Run: pip install pypdf"}), 500

        elif filename.endswith(".docx"):
            try:
                import docx, io
                doc = docx.Document(io.BytesIO(f.read()))
                text = "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                return jsonify({"ok": False, "error": "DOCX parsing not available. Run: pip install python-docx"}), 500

        else:
            return jsonify({"ok": False, "error": "Unsupported file type. Use PDF, DOCX, or TXT."}), 400

        # Clean up whitespace, truncate to 4k
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        text = text[:4000]

        return jsonify({"ok": True, "text": text})

    except Exception as e:
        log.error(f"Resume parse error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Blocked companies ─────────────────────────────────────────────────────
def load_blocked_companies() -> list:
    """Load blocked companies from data/blocked_companies.json."""
    if BLOCKED_COMPANIES_FILE.exists():
        try:
            return json.loads(BLOCKED_COMPANIES_FILE.read_text())
        except Exception:
            pass
    return []


def save_blocked_companies(companies: list) -> None:
    """Save blocked companies list to data/blocked_companies.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(BLOCKED_COMPANIES_FILE, json.dumps(companies, indent=2))


@app.route("/api/blocked-companies", methods=["GET"])
def get_blocked_companies():
    """Return the current blocked companies list."""
    return jsonify(load_blocked_companies())


@app.route("/api/blocked-companies", methods=["POST"])
def add_blocked_company():
    """Add a company to the blocked list. Body: {company: "name"}"""
    data = request.json or {}
    company = (data.get("company") or "").strip()
    if not company:
        return jsonify({"ok": False, "error": "company name required"}), 400
    companies = load_blocked_companies()
    if company.lower() not in [c.lower() for c in companies]:
        companies.append(company)
        save_blocked_companies(companies)
    return jsonify({"ok": True, "companies": companies})


@app.route("/api/blocked-companies/<company>", methods=["DELETE"])
def remove_blocked_company(company):
    """Remove a company from the blocked list."""
    companies = load_blocked_companies()
    companies = [c for c in companies if c.lower() != company.lower()]
    save_blocked_companies(companies)
    return jsonify({"ok": True, "companies": companies})


# ── Response tracking ──────────────────────────────────────────────────────
@app.route("/api/application/<app_id>/response", methods=["POST"])
def track_response(app_id):
    """
    Update response_status on an application.
    Body: {status: "got_response"|"interview"|"no_response"}
    """
    data = request.json or {}
    status = data.get("status", "no_response")
    valid = {"got_response", "interview", "no_response"}
    if status not in valid:
        return jsonify({"ok": False, "error": f"status must be one of {valid}"}), 400

    apps_file, idx, apps, a = find_app_any_date(app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404

    apps[idx]["response_status"] = status
    atomic_write(apps_file, json.dumps(apps, indent=2))
    return jsonify({"ok": True, "response_status": status})


# ── Check setup state ──────────────────────────────────────────────────────
@app.route("/api/status")
def setup_status():
    """Returns whether setup has been completed."""
    profile_exists = (ROOT / "config" / "profile.json").exists()
    env_exists = (ROOT / ".env").exists()
    return jsonify({
        "setup_complete": profile_exists and env_exists,
        "has_profile": profile_exists,
        "has_env": env_exists,
    })


# ── Serve dashboard HTML ───────────────────────────────────────────────────
@app.route("/")
@app.route("/dashboard")
def dashboard():
    # Redirect to setup if profile doesn't exist yet
    profile_file = ROOT / "config" / "profile.json"
    if not profile_file.exists():
        from flask import redirect
        return redirect("/setup")
    html_file = Path(__file__).parent / "index.html"
    if html_file.exists():
        return html_file.read_text()
    return '''<html><body style="background:#0d0d0f;color:#f0f0f5;font-family:sans-serif;
        display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:16px">
        <h2>Welcome to JobBot</h2>
        <p style="color:#9090a8">Complete setup first to get started.</p>
        <a href="/setup" style="background:#6c63ff;color:white;padding:12px 28px;
        border-radius:8px;text-decoration:none;font-weight:600">Start Setup →</a>
    </body></html>'''




# ── Scrape runner ──────────────────────────────────────────────────────────
import threading
import uuid

_scrape_jobs = {}  # job_id -> {status, log, started_at, finished_at, count}

def _scrape_worker(job_id: str, params: dict):
    """Run scraper in a background thread with custom params."""
    import sys as _sys
    import subprocess as _sp
    import json as _json
    from datetime import datetime as _dt

    _scrape_jobs[job_id]["status"] = "running"
    _scrape_jobs[job_id]["log"] = []

    def _log(msg):
        _scrape_jobs[job_id]["log"].append(msg)

    _log("Starting scrape...")

    # Build env for the scraper subprocess
    import os as _os
    env = {**_os.environ}
    env["JOBBOT_SOURCES"]         = _json.dumps(params.get("sources", []))
    env["JOBBOT_PER_SOURCE"]      = str(params.get("per_source", 10))
    env["JOBBOT_TOTAL_CAP"]       = str(params.get("total_cap", 80))
    env["JOBBOT_REQUIRE_KEYWORDS"] = _json.dumps(params.get("require_keywords", []))
    env["JOBBOT_EXCLUDE_KEYWORDS"] = _json.dumps(params.get("exclude_keywords", []))
    env["JOBBOT_MAX_AGE_DAYS"]    = str(params.get("max_age_days", 14))
    env["JOBBOT_SKIP_SEEN_COMPANIES"] = "1" if params.get("skip_seen_companies") else "0"

    scraper_path = ROOT / "scraper" / "scrape_jobs.py"
    drafter_path = ROOT / "drafter" / "draft_applications.py"

    try:
        # Step 1: Scrape
        _log("Scraping jobs from selected sources...")
        res = _sp.run(
            [_sys.executable, str(scraper_path)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=600, env=env
        )
        if res.stdout:
            for line in res.stdout.strip().splitlines()[-20:]:
                _log(line)
        if res.returncode != 0:
            _log(f"Scraper warning (exit {res.returncode}): {res.stderr[-300:] if res.stderr else ''}")
        else:
            _log("Scrape complete.")

        # Step 2: Draft
        _log("Drafting cover letters with AI...")
        draft_env = {**env}
        try:
            profile_data = _json.loads((ROOT / "config" / "profile.json").read_text())
            cap = profile_data.get("daily_app_cap", 10)
        except Exception:
            cap = 10
        draft_env["JOBBOT_DAILY_CAP"] = str(cap)

        res2 = _sp.run(
            [_sys.executable, str(drafter_path)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=1800, env=draft_env
        )
        if res2.stdout:
            for line in res2.stdout.strip().splitlines()[-10:]:
                _log(line)
        if res2.returncode != 0:
            _log(f"Drafter warning: {res2.stderr[-200:] if res2.stderr else ''}")
        else:
            _log("Drafting complete.")

        # Step 3: Score
        score_path = ROOT / "scraper" / "score_jobs.py"
        if score_path.exists():
            _sp.run([_sys.executable, str(score_path)], cwd=str(ROOT),
                    capture_output=True, text=True, timeout=120, env=env)
            _log("Scoring complete.")

        # Count how many apps were drafted today
        from datetime import date as _date
        apps_file = ROOT / "data" / "applications" / f"applications_{_date.today().isoformat()}.json"
        count = 0
        if apps_file.exists():
            try:
                count = len(_json.loads(apps_file.read_text()))
            except Exception:
                pass

        _scrape_jobs[job_id]["count"] = count
        _scrape_jobs[job_id]["status"] = "done"
        _log(f"Done! {count} applications ready to review.")

    except Exception as e:
        _scrape_jobs[job_id]["status"] = "error"
        _log(f"Error: {str(e)}")

    _scrape_jobs[job_id]["finished_at"] = _dt.now().isoformat()


@app.route("/api/run-scrape", methods=["POST"])
def run_scrape():
    """Kick off a background scrape+draft job."""
    params = request.json or {}
    job_id = str(uuid.uuid4())[:8]
    from datetime import datetime as _dt
    _scrape_jobs[job_id] = {
        "status": "queued",
        "log": [],
        "started_at": _dt.now().isoformat(),
        "finished_at": None,
        "count": 0,
    }
    t = threading.Thread(target=_scrape_worker, args=(job_id, params), daemon=True)
    t.start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/scrape-status/<job_id>")
def scrape_status(job_id):
    """Poll status of a running or completed scrape job."""
    job = _scrape_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify(job)


@app.route("/api/scrape-history")
def scrape_history_list():
    """Return all scrape job records."""
    return jsonify(list(_scrape_jobs.values()))


@app.route("/api/all-applications")
def all_applications():
    """
    Return every application across ALL dates, newest first.
    Used by the full history view.
    """
    all_apps = []
    for apps_file in sorted(APPS_DIR.glob("applications_*.json"), reverse=True):
        date_str = apps_file.stem.replace("applications_", "")
        try:
            apps = json.loads(apps_file.read_text())
            for a in apps:
                a["_date"] = date_str
            all_apps.extend(apps)
        except Exception:
            continue
    return jsonify(all_apps)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5555,
        debug=False,
        use_reloader=False,
        threaded=True,
    )
