#!/usr/bin/env python3
"""
JobBot — Morning email digest sender.
Sends a summary of today's drafted applications to the configured DIGEST_EMAIL.
Reads recipient from .env (DIGEST_EMAIL). Skips gracefully if SMTP not configured.
"""

import json
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
APPS_DIR = ROOT / "data" / "applications"
CONFIG_DIR = ROOT / "config"
load_dotenv(ROOT / ".env")


def load_profile():  # -> dict
    profile_path = CONFIG_DIR / "profile.json"
    if profile_path.exists():
        return json.loads(profile_path.read_text())
    return {}


def load_today_apps():  # -> list[dict]
    today = date.today().isoformat()
    f = APPS_DIR / f"applications_{today}.json"
    if not f.exists():
        files = sorted(APPS_DIR.glob("applications_*.json"), reverse=True)
        if not files:
            return []
        f = files[0]
    apps = json.loads(f.read_text())
    return sorted(apps, key=lambda a: a.get("score", 0), reverse=True)


def status_emoji(s):  # -> str
    return {"pending_review": "⏳", "sent": "✅", "skipped": "⛔", "approved": "🔵", "edited": "✏️"}.get(s, "⏳")


def build_html(apps, profile):  # -> str
    today_str = date.today().strftime("%A, %B %d")
    pending = len([a for a in apps if a["status"] == "pending_review"])
    first_name = profile.get("first_name") or profile.get("name", "").split()[0] or "there"

    rows = ""
    for i, a in enumerate(apps, 1):
        j = a["job"]
        rows += f"""
        <tr>
          <td style="padding:12px 8px;border-bottom:1px solid #2a2a35;font-weight:600;color:#f0f0f5;vertical-align:top">
            {i}. {j['title']}<br>
            <span style="color:#9090a8;font-weight:400;font-size:12px">{j['company']} · {j.get('location','')}</span>
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #2a2a35;color:#9090a8;font-size:12px;vertical-align:top">{j['source'].capitalize()}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #2a2a35;color:#6c63ff;font-weight:700;font-size:13px;vertical-align:top">{a.get('score',0):.1f}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #2a2a35;font-size:12px;vertical-align:top">{status_emoji(a['status'])} {a['status'].replace('_',' ').title()}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #2a2a35;vertical-align:top">
            <a href="http://localhost:5555" style="color:#6c63ff;font-size:12px">Review →</a>
          </td>
        </tr>
        """

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="background:#0d0d0f;color:#f0f0f5;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif;margin:0;padding:0">
  <div style="max-width:640px;margin:0 auto;padding:32px 24px">

    <!-- Header -->
    <div style="margin-bottom:28px">
      <div style="font-size:22px;font-weight:700;letter-spacing:-0.5px;margin-bottom:6px">
        Good morning, {first_name} 👋
      </div>
      <div style="color:#9090a8;font-size:14px">{today_str} · Your daily applications are ready</div>
    </div>

    <!-- Summary cards -->
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:28px">
      <div style="background:#16161a;border:1px solid #2a2a35;border-radius:10px;padding:16px;text-align:center">
        <div style="font-size:28px;font-weight:700;color:#6c63ff">{len(apps)}</div>
        <div style="font-size:11px;color:#9090a8;text-transform:uppercase;letter-spacing:0.5px">Drafted Today</div>
      </div>
      <div style="background:#16161a;border:1px solid #2a2a35;border-radius:10px;padding:16px;text-align:center">
        <div style="font-size:28px;font-weight:700;color:#f59e0b">{pending}</div>
        <div style="font-size:11px;color:#9090a8;text-transform:uppercase;letter-spacing:0.5px">Need Review</div>
      </div>
      <div style="background:#16161a;border:1px solid #2a2a35;border-radius:10px;padding:16px;text-align:center">
        <div style="font-size:28px;font-weight:700;color:#4ade80">{len(apps) - pending}</div>
        <div style="font-size:11px;color:#9090a8;text-transform:uppercase;letter-spacing:0.5px">Done</div>
      </div>
    </div>

    <!-- CTA -->
    <div style="margin-bottom:28px">
      <a href="http://localhost:5555" style="display:inline-block;background:#6c63ff;color:white;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:600;font-size:14px">
        Open Dashboard to Review →
      </a>
      <span style="font-size:12px;color:#9090a8;margin-left:12px">localhost:5555</span>
    </div>

    <!-- Table -->
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:28px">
      <thead>
        <tr>
          <th style="text-align:left;padding:8px;color:#5a5a72;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #2a2a35">Role</th>
          <th style="text-align:left;padding:8px;color:#5a5a72;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #2a2a35">Source</th>
          <th style="text-align:left;padding:8px;color:#5a5a72;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #2a2a35">Score</th>
          <th style="text-align:left;padding:8px;color:#5a5a72;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #2a2a35">Status</th>
          <th style="padding:8px;border-bottom:2px solid #2a2a35"></th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>

    <!-- Footer -->
    <div style="border-top:1px solid #2a2a35;padding-top:20px;font-size:12px;color:#5a5a72">
      To stop the daily runner, remove it from your login items or run:
      <code style="background:#16161a;padding:2px 6px;border-radius:4px;color:#9090a8">launchctl unload ~/Library/LaunchAgents/com.jobbot.plist</code>
      <br><br>
      <a href="https://www.perplexity.ai/computer" style="color:#5a5a72">Created with Perplexity Computer</a>
    </div>
  </div>
</body>
</html>
"""


def send_digest():
    profile = load_profile()
    apps = load_today_apps()
    if not apps:
        print("No applications to send.")
        return

    to_email = os.getenv("DIGEST_EMAIL", profile.get("email", ""))
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")

    if not smtp_user or not smtp_pass or not to_email:
        print("⚠️  SMTP not configured. Skipping email send.")
        print("   Add SMTP_USER, SMTP_PASS, and DIGEST_EMAIL to .env to enable email digests.")
        print("   Dashboard is available at http://localhost:5555")
        return

    today_str = date.today().strftime("%A, %b %d")
    subject = f"🎯 {len(apps)} applications ready for review — {today_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email

    html_body = build_html(apps, profile)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"✅ Digest sent to {to_email}")
    except Exception as e:
        print(f"❌ Email send failed: {e}")
        print("   Check SMTP settings in .env")


if __name__ == "__main__":
    send_digest()
