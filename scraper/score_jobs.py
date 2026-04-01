#!/usr/bin/env python3
"""
JobBot — Preference learning & job scoring.

Extracts features from jobs (company_type, role_keywords, industry, source),
maintains learned weights in data/preferences.json, and scores new jobs
based on accumulated approve/skip feedback.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
PREFS_FILE = DATA_DIR / "preferences.json"

log = logging.getLogger("score_jobs")


def atomic_write(path: Path, data: str) -> None:
    """Write data atomically: write to .tmp then rename, so crashes don't corrupt."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)

# ── Filler words to strip from titles ─────────────────────────────────────
FILLER_WORDS = {
    "the", "and", "for", "a", "an", "of", "in", "at", "to", "or", "is",
    "with", "on", "by", "as", "from", "this", "that", "it", "-", "/", "&",
    "|", "–", "—",
}

# ── Industry keyword map ──────────────────────────────────────────────────
INDUSTRY_KEYWORDS = {
    "sports": ["sports", "athletics", "esports", "fitness", "nfl", "nba",
               "mlb", "nhl", "soccer", "football", "basketball", "baseball",
               "hockey", "league", "stadium", "team", "coach", "athletic"],
    "media": ["media", "news", "journalism", "broadcast", "entertainment",
              "publishing", "editorial", "content", "podcast", "film",
              "television", "tv", "streaming", "video", "music", "radio"],
    "tech": ["software", "saas", "ai", "machine learning", "data science",
             "cloud", "devops", "engineering", "developer", "programming",
             "cybersecurity", "blockchain", "crypto", "startup", "app",
             "platform", "api", "tech", "technology", "fintech", "edtech"],
    "finance": ["finance", "banking", "investment", "hedge fund", "private equity",
                "venture capital", "vc", "accounting", "financial", "trading",
                "wealth", "asset", "portfolio", "insurance", "fintech",
                "credit", "mortgage", "bank"],
    "nonprofit": ["nonprofit", "non-profit", "ngo", "charity", "foundation",
                  "philanthropy", "social impact", "volunteer", "advocacy",
                  "community", "humanitarian", "cause"],
    "government": ["government", "federal", "state", "municipal", "public sector",
                   "usajobs", "city of", "county of", "department of",
                   "agency", "bureau", "administration", "congress",
                   "senate", "military", "defense"],
    "healthcare": ["healthcare", "health care", "medical", "hospital",
                   "pharmaceutical", "pharma", "biotech", "clinical",
                   "nursing", "patient", "therapy", "wellness", "dental",
                   "mental health"],
}

# ── Company type heuristics ───────────────────────────────────────────────
STARTUP_SIGNALS = [
    "startup", "seed", "series a", "series b", "early stage", "pre-seed",
    "yc ", "y combinator", "techstars", "venture-backed", "stealth",
    "founded 20", "inc.", "labs", "io", "hq",
]
CORPORATE_SIGNALS = [
    "corporation", "corp.", "global", "international", "worldwide",
    "group", "holdings", "enterprises", "fortune", "nasdaq", "nyse",
    "plc", "ltd", "gmbh", "s.a.",
]
AGENCY_SIGNALS = [
    "agency", "consulting", "consultancy", "partners", "advisors",
    "associates", "creative agency", "digital agency", "pr firm",
    "staffing", "recruiting", "talent",
]


def classify_company_type(company: str, description: str = "") -> str:
    """Classify company as startup, corporate, agency, or unknown."""
    text = f"{company} {description}".lower()
    scores = {"startup": 0, "corporate": 0, "agency": 0}
    for signal in STARTUP_SIGNALS:
        if signal in text:
            scores["startup"] += 1
    for signal in CORPORATE_SIGNALS:
        if signal in text:
            scores["corporate"] += 1
    for signal in AGENCY_SIGNALS:
        if signal in text:
            scores["agency"] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "unknown"


def extract_role_keywords(title: str) -> list[str]:
    """Extract meaningful keywords from a job title, stripping filler."""
    words = re.split(r"[\s\-/|,&()]+", title.lower())
    return [w for w in words if w and w not in FILLER_WORDS and len(w) > 1]


def classify_industry(title: str, description: str = "") -> str:
    """Classify job industry based on title + description keywords."""
    text = f"{title} {description}".lower()
    scores = {}
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text)
        if count > 0:
            scores[industry] = count
    if not scores:
        return "other"
    return max(scores, key=scores.get)


def extract_features(job: dict) -> dict:
    """Extract preference-relevant features from a job dict."""
    company = job.get("company", "")
    title = job.get("title", "")
    description = job.get("description", "")
    source = job.get("source", "")
    return {
        "company": company.lower().strip(),
        "company_type": classify_company_type(company, description),
        "role_keywords": extract_role_keywords(title),
        "industry": classify_industry(title, description),
        "source": source.lower().strip(),
    }


# ── Preferences I/O ──────────────────────────────────────────────────────

def load_preferences() -> dict:
    """Load preferences.json, creating a blank one if missing."""
    if PREFS_FILE.exists():
        try:
            return json.loads(PREFS_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "approved": [],
        "skipped": [],
        "weights": {
            "companies": {},
            "keywords": {},
            "industries": {},
            "sources": {},
        },
    }


def save_preferences(prefs: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(PREFS_FILE, json.dumps(prefs, indent=2))


# ── Weight updates ────────────────────────────────────────────────────────
WEIGHT_STEP = 1.0  # amount to increment/decrement per feedback


def record_feedback(action: str, job_data: dict) -> dict:
    """
    Record an approve or skip action and update weights.
    job_data should have: company, role_keywords, industry, source.
    Returns updated preferences.
    """
    prefs = load_preferences()
    features = {
        "company": job_data.get("company", ""),
        "role_keywords": job_data.get("role_keywords", []),
        "industry": job_data.get("industry", ""),
        "source": job_data.get("source", ""),
    }

    delta = WEIGHT_STEP if action == "approve" else -WEIGHT_STEP

    # Record in history
    bucket = "approved" if action == "approve" else "skipped"
    prefs[bucket].append(features)

    # Update weights
    w = prefs["weights"]

    company = features["company"].lower().strip()
    if company:
        w["companies"][company] = w["companies"].get(company, 0) + delta

    for kw in features.get("role_keywords", []):
        kw = kw.lower().strip()
        if kw:
            w["keywords"][kw] = w["keywords"].get(kw, 0) + delta

    industry = features.get("industry", "").lower().strip()
    if industry:
        w["industries"][industry] = w["industries"].get(industry, 0) + delta

    source = features.get("source", "").lower().strip()
    if source:
        w["sources"][source] = w["sources"].get(source, 0) + delta

    save_preferences(prefs)
    return prefs


# ── Scoring ───────────────────────────────────────────────────────────────

def score_job(job: dict, prefs: dict | None = None) -> float:
    """
    Score a single job based on learned weights.
    Returns the sum of weights for all matching features.
    All weights start at 0 (neutral), so untrained features contribute nothing.
    """
    if prefs is None:
        prefs = load_preferences()
    w = prefs["weights"]
    features = extract_features(job)

    score = 0.0

    # Company weight
    company = features["company"]
    if company in w["companies"]:
        score += w["companies"][company]

    # Keyword weights
    for kw in features["role_keywords"]:
        if kw in w["keywords"]:
            score += w["keywords"][kw]

    # Industry weight
    industry = features["industry"]
    if industry in w["industries"]:
        score += w["industries"][industry]

    # Source weight
    source = features["source"]
    if source in w["sources"]:
        score += w["sources"][source]

    return score


def score_all_jobs(jobs_file: Path | None = None) -> list[dict]:
    """
    Score all jobs in the given file (or today's applications file).
    Updates each job dict with a 'preference_score' field and re-saves.
    Returns the updated list.
    """
    from datetime import date as _date

    if jobs_file is None:
        apps_dir = DATA_DIR / "applications"
        files = sorted(apps_dir.glob("applications_*.json"), reverse=True)
        if not files:
            log.info("No applications files found to score")
            return []
        jobs_file = files[0]

    if not jobs_file.exists():
        log.warning(f"Jobs file not found: {jobs_file}")
        return []

    apps = json.loads(jobs_file.read_text())
    prefs = load_preferences()

    for app in apps:
        job = app.get("job", app)  # applications have job nested
        app["preference_score"] = score_job(job, prefs)

    atomic_write(jobs_file, json.dumps(apps, indent=2))
    log.info(f"Scored {len(apps)} jobs in {jobs_file.name}")
    return apps


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    apps = score_all_jobs()
    if apps:
        print(f"\nScored {len(apps)} applications:")
        for a in sorted(apps, key=lambda x: x.get("preference_score", 0), reverse=True)[:10]:
            job = a.get("job", a)
            ps = a.get("preference_score", 0)
            print(f"  [{ps:+.1f}] {job.get('title', '?')[:45]:45} @ {job.get('company', '?')[:30]}")
    else:
        print("No applications to score.")
