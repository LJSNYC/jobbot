#!/usr/bin/env python3
"""
JobBot — Master runner.
Called by macOS launchd on first login each day (or run manually).
1. Scrapes jobs from multiple sources
2. Drafts applications with AI cover letters
3. Sends email digest (optional)
4. Opens dashboard in browser
"""

import logging
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from datetime import datetime, date

ROOT = Path(__file__).parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "runner.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("runner")


def run_step(name, script):  # -> bool
    log.info(f"▶ Starting: {name}")
    try:
        result = subprocess.run(
            [sys.executable, script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=1800  # 30 min max per step
        )
        if result.returncode == 0:
            log.info(f"✅ {name} complete")
            if result.stdout:
                log.info(result.stdout[-500:])
        else:
            log.error(f"❌ {name} failed (exit {result.returncode})")
            if result.stderr:
                log.error(result.stderr[-500:])
            return False
    except subprocess.TimeoutExpired:
        log.error(f"⏱ {name} timed out after 30 minutes")
        return False
    except Exception as e:
        log.error(f"❌ {name} exception: {e}")
        return False
    return True


def start_dashboard():
    """Start the dashboard server in background if not already running."""
    import socket
    port = 5555
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("localhost", port)) == 0:
            log.info("Dashboard already running on :5555")
            return

    log.info("Starting dashboard server...")
    subprocess.Popen(
        [sys.executable, str(ROOT / "dashboard" / "server.py")],
        cwd=str(ROOT),
        stdout=open(LOG_DIR / "dashboard.log", "a"),
        stderr=subprocess.STDOUT,
    )
    time.sleep(2)


def check_setup():
    """Check if setup wizard has been completed."""
    profile_path = ROOT / "config" / "profile.json"
    env_path = ROOT / ".env"
    return profile_path.exists() and env_path.exists()


def main():
    log.info(f"\n{'='*60}")
    log.info(f"JobBot — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info(f"{'='*60}\n")

    # Once-per-day guard
    lock_file = LOG_DIR / f"ran_{date.today().isoformat()}.lock"
    if lock_file.exists():
        log.info("Already ran today — skipping. Delete lock file to force re-run.")
        start_dashboard()
        time.sleep(1)
        webbrowser.open("http://localhost:5555")
        return
    lock_file.touch()

    # Check setup
    if not check_setup():
        log.info("Setup not complete — opening setup wizard")
        start_dashboard()
        time.sleep(2)
        webbrowser.open("http://localhost:5555/setup")
        return

    # Step 1: Scrape
    scrape_ok = run_step("Job Scraper", str(ROOT / "scraper" / "scrape_jobs.py"))
    if not scrape_ok:
        log.warning("Scraper had issues — continuing to draft with whatever was found")

    # Step 2: Draft
    draft_ok = run_step("Application Drafter", str(ROOT / "drafter" / "draft_applications.py"))
    if not draft_ok:
        log.error("Drafter failed — check logs/drafter.log")

    # Step 3: Email digest (optional — skips gracefully if SMTP not configured)
    run_step("Email Digest", str(ROOT / "drafter" / "send_digest.py"))

    # Step 4: Open dashboard
    start_dashboard()
    time.sleep(2)
    webbrowser.open("http://localhost:5555")

    log.info("\n✅ JobBot complete. Dashboard open at http://localhost:5555\n")


if __name__ == "__main__":
    main()
