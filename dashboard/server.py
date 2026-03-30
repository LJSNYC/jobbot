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

load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dashboard")

app = Flask(__name__)
CORS(app)


# ── Helpers ────────────────────────────────────────────────────────────────
def get_latest_apps_file():  # -> Path | None
    files = sorted(APPS_DIR.glob("applications_*.json"), reverse=True)
    return files[0] if files else None


def load_apps(date_str=None):  # -> list[dict]
    if date_str:
        f = APPS_DIR / f"applications_{date_str}.json"
    else:
        f = get_latest_apps_file()
    if not f or not f.exists():
        return []
    return json.loads(f.read_text())


def save_apps(apps, date_str=None):
    if not date_str:
        f = get_latest_apps_file()
        if not f:
            f = APPS_DIR / f"applications_{date.today().isoformat()}.json"
    else:
        f = APPS_DIR / f"applications_{date_str}.json"
    f.write_text(json.dumps(apps, indent=2))


def find_app(apps, app_id):  # -> tuple[int, dict | None]
    for i, a in enumerate(apps):
        if a["id"] == app_id:
            return i, a
    return -1, None


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
        })
    summary.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(summary)


@app.route("/api/application/<app_id>")
def get_application(app_id):
    apps = load_apps()
    _, a = find_app(apps, app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404
    # Include live preference score
    prefs = load_preferences()
    a["preference_score"] = a.get("preference_score", score_job(a.get("job", {}), prefs))
    return jsonify(a)


@app.route("/api/application/<app_id>", methods=["PATCH"])
def update_application(app_id):
    apps = load_apps()
    idx, a = find_app(apps, app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404

    data = request.json
    allowed = ["cover_letter", "about_me", "notes", "status"]
    for k in allowed:
        if k in data:
            apps[idx][k] = data[k]

    save_apps(apps)
    return jsonify({"ok": True, "updated": app_id})


@app.route("/api/application/<app_id>/approve", methods=["POST"])
def approve_application(app_id):
    """Mark as approved and open apply URL in browser."""
    apps = load_apps()
    idx, a = find_app(apps, app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404

    apps[idx]["status"] = "approved"
    save_apps(apps)

    apply_url = a["apply_info"]["apply_url"]
    return jsonify({
        "ok": True,
        "apply_url": apply_url,
        "prefill": a["apply_info"].get("prefill", {}),
        "cover_letter": a["cover_letter"],
        "about_me": a["about_me"]
    })


@app.route("/api/application/<app_id>/mark_sent", methods=["POST"])
def mark_sent(app_id):
    apps = load_apps()
    idx, a = find_app(apps, app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404

    apps[idx]["status"] = "sent"
    apps[idx]["sent_at"] = datetime.now().isoformat()
    save_apps(apps)

    sent_log = SENT_DIR / "sent_log.json"
    existing = json.loads(sent_log.read_text()) if sent_log.exists() else []
    existing.append({
        "id": app_id,
        "title": a["job"]["title"],
        "company": a["job"]["company"],
        "url": a["job"]["url"],
        "sent_at": apps[idx]["sent_at"]
    })
    sent_log.write_text(json.dumps(existing, indent=2))

    return jsonify({"ok": True, "sent_at": apps[idx]["sent_at"]})


@app.route("/api/application/<app_id>/skip", methods=["POST"])
def skip_application(app_id):
    apps = load_apps()
    idx, a = find_app(apps, app_id)
    if not a:
        return jsonify({"error": "Not found"}), 404
    apps[idx]["status"] = "skipped"
    save_apps(apps)
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
        apps = load_apps()
        idx, a = find_app(apps, job_id)
        if a is not None:
            new_status = "approved" if action == "approve" else "skipped"
            apps[idx]["status"] = new_status
            apps[idx]["preference_score"] = score_job(a.get("job", {}), prefs)
            save_apps(apps)

    return jsonify({"ok": True, "action": action, "weights": prefs["weights"]})


@app.route("/api/stats")
def stats():
    sent_log = SENT_DIR / "sent_log.json"
    sent = json.loads(sent_log.read_text()) if sent_log.exists() else []

    apps_files = sorted(APPS_DIR.glob("applications_*.json"), reverse=True)
    today_apps = load_apps()

    pending = len([a for a in today_apps if a["status"] == "pending_review"])
    approved = len([a for a in today_apps if a["status"] in ["approved", "sent"]])
    skipped = len([a for a in today_apps if a["status"] == "skipped"])

    return jsonify({
        "total_sent": len(sent),
        "today_pending": pending,
        "today_approved": approved,
        "today_skipped": skipped,
        "days_active": len(apps_files),
        "recent_sent": sent[-5:][::-1]
    })


@app.route("/api/dates")
def available_dates():
    files = sorted(APPS_DIR.glob("applications_*.json"), reverse=True)
    dates = [f.stem.replace("applications_", "") for f in files]
    return jsonify(dates)


@app.route("/api/history")
def application_history():
    """
    Return all applications Leo has ever marked as sent, across all dates.
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
                if a.get("status") in ("sent", "approved"):
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
        }
        if rid in cover_letters:
            entry.update(cover_letters[rid])
        history.append(entry)

    # Also include approved-but-not-in-sent-log (e.g. approved this session)
    for rid, data in cover_letters.items():
        if rid not in seen_ids:
            history.append({"id": rid, **data, "sent_at": "", "apply_url": data.get("apply_url", "")})

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
    html_file = Path(__file__).parent / "index.html"
    if html_file.exists():
        return html_file.read_text()
    # No dashboard yet — redirect to setup
    return '''<html><body style="background:#0d0d0f;color:#f0f0f5;font-family:sans-serif;
        display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:16px">
        <h2>Welcome to JobBot</h2>
        <p style="color:#9090a8">Complete setup first to get started.</p>
        <a href="/setup" style="background:#6c63ff;color:white;padding:12px 28px;
        border-radius:8px;text-decoration:none;font-weight:600">Start Setup →</a>
    </body></html>'''


# ── Run ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "5555"))

    # Check if first-time setup is needed
    profile_path = ROOT / "config" / "profile.json"
    if not profile_path.exists():
        print(f"\n🚀 JobBot Dashboard")
        print(f"   First run detected — opening setup wizard")
        print(f"   http://localhost:{port}/setup\n")
        import threading
        def _open():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{port}/setup")
        threading.Thread(target=_open, daemon=True).start()
    else:
        print(f"\n🚀 JobBot Dashboard")
        print(f"   Opening http://localhost:{port}")
        import threading
        def _open():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=_open, daemon=True).start()

    app.run(host="127.0.0.1", port=port, debug=False)
