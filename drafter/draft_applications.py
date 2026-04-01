#!/usr/bin/env python3
"""
AI application drafter for JobBot.
Reads today's scraped jobs, scores relevance, picks top 10,
generates tailored cover letters and application summaries.
"""
from __future__ import annotations

import os
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
from openai import OpenAI
from dotenv import load_dotenv

# ── Spend guardrail ────────────────────────────────────────────────────────
DAILY_SPEND_LIMIT = 0.45   # Hard stop at $0.45 (well under $0.50)
PER_CALL_MAX_TOKENS = 500  # Cap per cover letter / about-me generation

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

def check_spend_limit(api_key):  # -> tuple[bool, float]
    """
    Returns (ok_to_proceed, current_spend).
    ok_to_proceed is False if we're at or over the daily limit.
    """
    spend = get_todays_spend(api_key)
    log.info(f"Today's OpenAI spend so far: ${spend:.4f} (limit: ${DAILY_SPEND_LIMIT}")
    if spend >= DAILY_SPEND_LIMIT:
        log.warning(f"🚨 Daily spend limit reached (${spend:.4f} >= ${DAILY_SPEND_LIMIT}). Stopping AI generation.")
        return False, spend
    return True, spend

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
APPS_DIR = DATA_DIR / "applications"
APPS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR = ROOT / "config"
LOG_DIR = ROOT / "logs"

TODAY = date.today().isoformat()
TODAY_JOBS_FILE = JOBS_DIR / f"jobs_{TODAY}.json"
TODAY_APPS_FILE = APPS_DIR / f"applications_{TODAY}.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "drafter.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("drafter")

load_dotenv(ROOT / ".env")


def atomic_write(path: Path, data: str) -> None:
    """Write data atomically: write to .tmp then rename, so crashes don't corrupt."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


# ── Load profile ───────────────────────────────────────────────────────────
def load_profile() -> dict:
    p = CONFIG_DIR / "profile.json"
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, ValueError):
        raise RuntimeError(
            "profile.json is missing or corrupted — "
            "re-run setup at http://localhost:5555/setup"
        )

def load_resume() -> str:
    return (CONFIG_DIR / "resume.txt").read_text()

# ── OpenAI client ──────────────────────────────────────────────────────────
def get_client():  # -> OpenAI
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "sk-YOUR_KEY_HERE":
        raise RuntimeError("OPENAI_API_KEY not set in .env")
    return OpenAI(api_key=api_key)

# ── Score job relevance ────────────────────────────────────────────────────
# ── Borough filter & scoring ──────────────────────────────────────────────
BOROUGH_WHITELIST = [
    "brooklyn", "manhattan", "queens", "staten island",
    "new york, ny", "new york city", "nyc", "new york, new york"
]
# These get a score BOOST (Brooklyn + Manhattan below 125th are priority)
PRIORITY_BOROUGHS = ["brooklyn", "manhattan"]
# Hard-exclude uptown Manhattan
UPTOWN_SIGNALS = ["harlem", "washington heights", "inwood", "bronx"]

def is_allowed_location(job):
    """
    Returns True if the job is in an allowed NYC borough.
    Filters OUT: Bronx, uptown Manhattan (125th+), NJ, CT, remote-only outside NYC.
    """
    loc = (job.get("location") or "").lower()
    desc = (job.get("description") or "").lower()
    combined = loc + " " + desc[:300]

    # Hard excludes
    for signal in UPTOWN_SIGNALS:
        if signal in loc:  # only check location field for uptown, not full desc
            return False

    # Must match at least one allowed borough/city
    for borough in BOROUGH_WHITELIST:
        if borough in combined:
            return True

    # If location is blank or just "New York" assume ok
    if not loc or loc.strip() in ["", "new york", "ny"]:
        return True

    return False

def borough_score_bonus(job):
    """Extra points for Brooklyn and lower Manhattan jobs."""
    loc = (job.get("location") or "").lower()
    desc = (job.get("description") or "").lower()
    combined = loc + " " + desc[:200]
    if "brooklyn" in combined:
        return 1.5
    if "manhattan" in combined:
        return 1.0
    return 0.0

def score_job(job, profile):  # was: score_job(job: dict, profile: dict) -> float:
    """Heuristic score 0-10 for how good a fit this job is for the applicant."""
    score = 5.0
    title = job.get("title", "").lower()
    desc = job.get("description", "").lower()
    combined = title + " " + desc

    # Positive signals
    good_terms = [
        "intern", "internship", "summer", "startup", "growth", "marketing",
        "sales", "business development", "operations", "venture", "vc",
        "product", "generalist", "founder", "early stage", "social media",
        "content", "brand", "partnerships", "strategy", "analyst", "associate",
        "entrepreneur", "innovation", "technology", "digital", "e-commerce"
    ]
    for term in good_terms:
        if term in combined:
            score += 0.3

    # NYC borough weight + priority bonus
    score += borough_score_bonus(job)

    # Paid signal
    pay_terms = ["paid", "stipend", "compensation", "salary", "$", "hourly"]
    for term in pay_terms:
        if term in combined:
            score += 0.5

    # Negative signals
    bad_terms = ["unpaid", "volunteer", "no compensation", "academic credit only"]
    for term in bad_terms:
        if term in combined:
            score -= 3.0

    senior_terms = ["senior", "sr.", "director", "vp ", "vice president", "manager", "principal", "staff engineer"]
    for term in senior_terms:
        if term in title:
            score -= 5.0

    return min(max(score, 0), 10)


# ── Generate cover letter ──────────────────────────────────────────────────
def build_system_prompt(profile: dict, resume: str) -> str:
    name = profile.get("name", "the applicant")
    university = profile.get("university", "")
    major = profile.get("major", "")
    grad_year = profile.get("grad_year", "")
    location = profile.get("location", "")
    linkedin = profile.get("linkedin", "")
    avail_start = profile.get("availability_start", "")
    avail_end = profile.get("availability_end", "")
    extra = profile.get("extra_context", "")
    role_types = ", ".join(profile.get("role_types", []))
    availability = f"{avail_start} to {avail_end}" if avail_start and avail_end else "this summer"

    return f"""You are a career coach and ghostwriter helping {name} land a job or internship.

Applicant profile:
- Name: {name}
- University: {university}, graduating {grad_year}
- Major: {major}
- Based in: {location}
- Interested in: {role_types}
- Available: {availability}
- LinkedIn: {linkedin}
{f'- Additional context: {extra}' if extra else ''}

Resume:
{resume[:2000]}

WRITING STYLE:
- Match the tone to the role: startup-casual for startups, more polished for corporates
- Lead with a strong, specific hook tied to THIS company or role — never generic openers
- Weave in concrete specifics from the resume naturally
- 3 tight paragraphs, max 250 words
- Sound like an ambitious, self-aware person who does their homework
- End with a confident, low-pressure close
- No clichés: never start with "I am writing to express my interest..."
"""

def generate_cover_letter(job, profile, resume, client):
    name = profile.get("name", "")
    phone = profile.get("phone", "")
    email = profile.get("email", "")
    linkedin = profile.get("linkedin", "").replace("https://", "").replace("http://", "")
    system_prompt = build_system_prompt(profile, resume)

    desc = job.get("description", "")
    if not desc:
        desc = f"Role: {job['title']} at {job['company']}. No description available."

    prompt = f"""Write a tailored cover letter for {name} applying to this role:

JOB TITLE: {job['title']}
COMPANY: {job['company']}
LOCATION: {job.get('location', '')}
JOB DESCRIPTION:
{desc[:2000]}

Instructions:
- Open with something specific to this company or role (show you know them)
- Highlight the 2-3 most relevant things from the resume for THIS specific role
- Make it feel authentic and energetic, not corporate
- 3 paragraphs, ~200-250 words
- Do not include "Dear Hiring Manager" or formal salutations — just start with the first paragraph
- End with: "{name} | {phone} | {email} | {linkedin}"
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=PER_CALL_MAX_TOKENS,  # Hard cap — never exceeds this
        temperature=0.75
    )
    return response.choices[0].message.content.strip()


def generate_about_me(job, profile, client):
    name = profile.get("name", "")
    avail_start = profile.get("availability_start", "")
    avail_end = profile.get("availability_end", "")
    availability = f"{avail_start} to {avail_end}" if avail_start and avail_end else "this summer"
    system_prompt = build_system_prompt(profile, "")
    desc = job.get("description", "")

    prompt = f"""Write a short "About Me" / personal statement (2-3 sentences, ~60 words) for {name} for this specific role:

JOB TITLE: {job['title']}
COMPANY: {job['company']}
DESCRIPTION SNIPPET: {desc[:500]}

It should:
- Start with who they are (student, background, key strength)
- Mention 1-2 things most relevant to THIS role
- Sound confident and genuine, not generic
- End with availability: {availability}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=min(150, PER_CALL_MAX_TOKENS),  # Hard cap
        temperature=0.7
    )
    return response.choices[0].message.content.strip()


def generate_fit_summary(job, profile, client):
    """Short 2-sentence summary of why the applicant is a fit."""
    name = profile.get("name", "The applicant")
    desc = job.get("description", "No description available.")
    system_prompt = build_system_prompt(profile, "")

    prompt = f"""In 2 sentences max, explain why {name} is a strong fit for this role. Be specific — reference actual things from their background that match the job requirements. Keep it punchy.

JOB: {job['title']} at {job['company']}
DESCRIPTION: {desc[:800]}
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=min(100, PER_CALL_MAX_TOKENS),  # Hard cap
        temperature=0.6
    )
    return response.choices[0].message.content.strip()


# ── Detect apply method ────────────────────────────────────────────────────
def detect_apply_method(job, profile):  # job: dict, profile: dict -> dict
    """Figure out how to apply and what fields are likely needed."""
    source = job.get("source", "")
    url = job.get("url", "")

    method = {
        "type": "external_link",
        "apply_url": url,
        "prefill": {
            "first_name": profile.get("first_name", ""),
            "last_name": profile.get("last_name", ""),
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "linkedin": profile.get("linkedin", ""),
            "university": profile.get("university", ""),
            "graduation_year": profile.get("grad_year", ""),
            "major": profile.get("major", ""),
            "location": profile.get("location", ""),
            "gpa": profile.get("gpa", ""),
            "start_date": profile.get("availability_start", ""),
            "end_date": profile.get("availability_end", ""),
        }
    }

    if source == "linkedin":
        method["type"] = "linkedin_easy_apply"
        method["apply_url"] = url
    elif source == "handshake":
        method["type"] = "handshake_apply"
        method["apply_url"] = url

    return method


# ── Main draft pipeline ────────────────────────────────────────────────────
def run_drafter(num_apps: int = 10) -> list[dict]:
    # Load today's jobs
    if not TODAY_JOBS_FILE.exists():
        log.error(f"No jobs file found for today: {TODAY_JOBS_FILE}")
        # Try the most recent file
        job_files = sorted(JOBS_DIR.glob("jobs_*.json"), reverse=True)
        if not job_files:
            log.error("No job files found at all. Run the scraper first.")
            return []
        log.info(f"Using most recent: {job_files[0]}")
        jobs = json.loads(job_files[0].read_text())
    else:
        jobs = json.loads(TODAY_JOBS_FILE.read_text())

    log.info(f"Loaded {len(jobs)} jobs")

    profile = load_profile()
    resume = load_resume()

    api_key = os.getenv("OPENAI_API_KEY", "")
    try:
        client = get_client()
        use_ai = True
        # Pre-flight spend check
        ok, current_spend = check_spend_limit(api_key)
        if not ok:
            log.warning(f"Skipping AI generation — already at daily limit (${current_spend:.4f})")
            use_ai = False
        else:
            remaining = DAILY_SPEND_LIMIT - current_spend
            log.info(f"Spend headroom: ${remaining:.4f} remaining today")
    except RuntimeError as e:
        log.warning(f"OpenAI not available: {e}. Will use placeholder drafts.")
        use_ai = False
        client = None
        current_spend = 0.0

    # Borough filter — only keep allowed NYC locations
    before = len(jobs)
    jobs = [j for j in jobs if is_allowed_location(j)]
    log.info(f"Borough filter: {before} → {len(jobs)} jobs (removed {before - len(jobs)} outside target boroughs)")

    # Score and rank
    for job in jobs:
        job["score"] = score_job(job, profile)

    ranked = sorted(jobs, key=lambda j: j["score"], reverse=True)
    top_jobs = ranked[:num_apps]

    log.info(f"Top {len(top_jobs)} jobs selected for drafting")

    applications = []
    for i, job in enumerate(top_jobs, 1):
        log.info(f"Drafting {i}/{len(top_jobs)}: {job['title']} @ {job['company']}")

        if use_ai:
            # Re-check spend before each job (belt-and-suspenders)
            ok, current_spend = check_spend_limit(api_key)
            if not ok:
                log.warning(f"Hit spend limit mid-run at job {i}. Switching to placeholders for remaining.")
                use_ai = False

        if use_ai:
            try:
                cover_letter = generate_cover_letter(job, profile, resume, client)
                about_me = generate_about_me(job, profile, client)
                fit_summary = generate_fit_summary(job, profile, client)
            except Exception as e:
                log.error(f"AI generation failed for {job['id']}: {e}")
                cover_letter = f"[Cover letter generation failed: {e}]"
                about_me = f"{profile.get('name','')} — available {profile.get('availability_start','')} to {profile.get('availability_end','')}"
                fit_summary = "Strong fit based on background and relevant experience."
        else:
            name = profile.get('name', '')
            email = profile.get('email', '')
            phone = profile.get('phone', '')
            cover_letter = (
                f"[DRAFT — Add your OpenAI API key to .env to enable AI generation]\n\n"
                f"Application for {job['title']} at {job['company']}.\n\n"
                f"{name} | {phone} | {email}"
            )
            about_me = f"{name}, {profile.get('major','')} student at {profile.get('university','')}, available {profile.get('availability_start','')} to {profile.get('availability_end','')}"
            fit_summary = "Add your OpenAI API key to generate AI-powered fit summaries."

        apply_info = detect_apply_method(job, profile)

        application = {
            "id": job["id"],
            "job": job,
            "cover_letter": cover_letter,
            "about_me": about_me,
            "fit_summary": fit_summary,
            "apply_info": apply_info,
            "score": job["score"],
            "status": "pending_review",  # pending_review, approved, edited, sent, skipped
            "drafted_at": datetime.now().isoformat(),
            "sent_at": None,
            "notes": ""
        }
        applications.append(application)

    # Save
    atomic_write(TODAY_APPS_FILE, json.dumps(applications, indent=2))
    log.info(f"Saved {len(applications)} drafted applications to {TODAY_APPS_FILE}")

    return applications


if __name__ == "__main__":
    apps = run_drafter()
    print(f"\n✅ Drafted {len(apps)} applications")
    for a in apps[:3]:
        print(f"\n{'='*60}")
        print(f"[{a['score']:.1f}/10] {a['job']['title']} @ {a['job']['company']}")
        print(f"URL: {a['job']['url']}")
        print(f"\nCOVER LETTER:\n{a['cover_letter'][:400]}...")  # noqa: E501
