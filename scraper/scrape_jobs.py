#!/usr/bin/env python3
from __future__ import annotations
"""
JobBot scraper — RSS/API edition.
No headless browser needed. Uses:
  - Indeed RSS feeds (no auth, very reliable)
  - LinkedIn public job search JSON (no auth)
  - Wellfound public listings
  - Handshake public API
  - SimplyHired search
  - Internships.com
Reads job preferences from config/profile.json for dynamic queries.
"""

import hashlib
import json
import logging
import os
import time
import random
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "jobs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SEEN_FILE = DATA_DIR / "seen_ids.json"
TODAY_FILE = DATA_DIR / f"jobs_{date.today().isoformat()}.json"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
CONFIG_DIR = ROOT / "config"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scraper.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("scraper")

load_dotenv(ROOT / ".env")


def atomic_write(path: Path, data: str) -> None:
    """Write data atomically: write to .tmp then rename, so crashes don't corrupt."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Load profile ───────────────────────────────────────────────────────────
def load_profile():  # -> dict
    profile_path = CONFIG_DIR / "profile.json"
    if profile_path.exists():
        return json.loads(profile_path.read_text())
    return {}


def build_search_queries(profile):  # -> list[str]
    """
    Build Indeed/SimplyHired search query strings from profile preferences.
    Returns a list of URL-encoded query strings.
    """
    job_types = profile.get("job_types", ["Internship"])
    role_types = profile.get("role_types", [])
    industries = profile.get("industries", "")
    avail_start = profile.get("availability_start", "")

    # Extract year from start date for "summer XXXX" queries
    year_tag = ""
    if avail_start:
        try:
            year_tag = avail_start[:4]  # "2026" from "2026-05-10"
        except Exception:
            pass

    base_type = "intern" if any("intern" in jt.lower() for jt in job_types) else "entry+level"
    season = f"summer+{year_tag}" if year_tag else "summer"

    queries = [
        f"{season}+{base_type}",
        f"paid+{base_type}+{season}",
        f"startup+{base_type}+{season}",
    ]

    # Add role-specific queries
    role_map = {
        "Marketing": "marketing+intern",
        "Business Development": "business+development+intern",
        "Operations": "operations+intern",
        "Product": "product+intern",
        "Software Engineering": "software+engineer+intern",
        "Data / Analytics": "data+analyst+intern",
        "Sales": "sales+intern",
        "Finance": "finance+intern",
        "Design": "design+intern",
        "Research": "research+intern",
        "Startup / Generalist": "generalist+intern+startup",
        "VC / Investing": "venture+capital+intern",
    }
    for role in role_types[:4]:  # cap at 4 role queries
        if role in role_map:
            q = role_map[role] + (f"+{year_tag}" if year_tag else "")
            queries.append(q.replace(" ", "+"))

    # Add industry queries if specified
    if industries:
        for ind in industries.split(",")[:2]:
            ind_clean = ind.strip().lower().replace(" ", "+")
            if ind_clean:
                queries.append(f"{ind_clean}+intern+{year_tag}" if year_tag else f"{ind_clean}+intern")

    return queries[:10]  # max 10 queries


def get_location_param(profile):  # -> str (URL-encoded city, state)
    loc = profile.get("location_preference", "New York, NY")
    if not loc:
        loc = "New York, NY"
    return requests.utils.quote(loc)


# ── Seen IDs ───────────────────────────────────────────────────────────────
def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except (json.JSONDecodeError, ValueError):
            log.warning("seen_ids.json is corrupted — starting with empty seen set")
            return set()
    return set()


def save_seen(seen):
    atomic_write(SEEN_FILE, json.dumps(list(seen), indent=2))


def job_id(url, title, company):
    raw = f"{url}{title}{company}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def human_delay(lo=0.8, hi=2.0):
    time.sleep(random.uniform(lo, hi))


def is_senior(title):
    title_l = title.lower()
    skip = ["senior", "sr.", "director", "vp ", "vice president",
            "manager", "staff ", "principal", "head of", "lead "]
    return any(w in title_l for w in skip)


def looks_paid(text):
    """Heuristic — return False only if explicitly unpaid."""
    text_l = text.lower()
    unpaid_signals = ["unpaid", "no compensation", "academic credit only",
                      "for credit only", "volunteer", "stipend: none"]
    return not any(s in text_l for s in unpaid_signals)


# ── 1. Indeed RSS ──────────────────────────────────────────────────────────
def scrape_indeed_rss(seen, profile, limit=20):
    log.info("Scraping Indeed (RSS)...")
    results = []
    loc_param = get_location_param(profile)
    queries = build_search_queries(profile)

    for q in queries:
        if len(results) >= limit:
            break
        url = (
            f"https://www.indeed.com/rss?"
            f"q={q}&l={loc_param}&jt=internship&fromage=14&sort=date"
        )
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                log.warning(f"Indeed RSS {q}: status {resp.status_code}")
                continue

            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            log.info(f"Indeed RSS '{q}': {len(items)} items")

            for item in items:
                try:
                    title = (item.findtext("title") or "").strip()
                    link  = (item.findtext("link")  or "").strip()
                    desc  = (item.findtext("description") or "").strip()
                    company_el = item.find("{https://www.indeed.com/about/}company")
                    company = company_el.text.strip() if company_el is not None else ""
                    loc_el = item.find("{https://www.indeed.com/about/}city")
                    location = loc_el.text.strip() if loc_el is not None else profile.get("location_preference", "")

                    desc_text = BeautifulSoup(desc, "html.parser").get_text(" ", strip=True)[:2000]

                    if not title or not link:
                        continue
                    if is_senior(title):
                        continue
                    if profile.get("paid_only", True) and not looks_paid(desc_text):
                        continue

                    jid = job_id(link, title, company)
                    if jid in seen:
                        continue

                    results.append({
                        "id": jid,
                        "source": "indeed",
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": link,
                        "description": desc_text,
                        "scraped_at": datetime.now().isoformat(),
                        "applied": False,
                        "status": "new"
                    })
                    seen.add(jid)

                except Exception as e:
                    log.debug(f"Indeed item parse error: {e}")
                    continue

            human_delay(1, 2)

        except Exception as e:
            log.warning(f"Indeed RSS query '{q}' failed: {e}")
            continue

    log.info(f"Indeed RSS: {len(results)} jobs")
    return results[:limit]


# ── 2. LinkedIn public job search ──────────────────────────────────────────
def scrape_linkedin_public(seen, profile, limit=20):
    log.info("Scraping LinkedIn (public search)...")
    results = []

    loc_pref = profile.get("location_preference", "New York, NY")
    role_types = profile.get("role_types", [])
    year_tag = ""
    if profile.get("availability_start"):
        year_tag = profile["availability_start"][:4]

    base_queries = [
        f"summer {year_tag} internship" if year_tag else "summer internship",
        f"summer intern {year_tag} startup" if year_tag else "summer intern startup",
        f"paid intern marketing {year_tag}" if year_tag else "paid intern marketing",
    ]
    # Add role-specific
    for role in role_types[:3]:
        base_queries.append(f"{role.lower()} intern {year_tag}".strip())

    queries = [(q, loc_pref) for q in base_queries[:6]]

    session = requests.Session()
    session.headers.update(HEADERS)

    for keywords, location in queries:
        if len(results) >= limit:
            break
        try:
            url = (
                "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={requests.utils.quote(keywords)}"
                f"&location={requests.utils.quote(location)}"
                f"&f_JT=I"       # Internship
                f"&f_TPR=r604800" # Last 7 days
                f"&start=0"
            )
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                url2 = (
                    "https://www.linkedin.com/jobs/search/"
                    f"?keywords={requests.utils.quote(keywords)}"
                    f"&location={requests.utils.quote(location)}"
                    f"&f_JT=I&f_TPR=r604800"
                )
                resp = session.get(url2, timeout=15)
                if resp.status_code != 200:
                    log.warning(f"LinkedIn public '{keywords}': {resp.status_code}")
                    continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(
                "div.base-card, li.jobs-search-results__list-item, "
                "div.job-search-card, article.job-card"
            )
            log.info(f"LinkedIn public '{keywords}': {len(cards)} cards")

            for card in cards[:10]:
                try:
                    title_el   = card.select_one("h3, h4, .base-search-card__title, .job-card-list__title")
                    company_el = card.select_one(".base-search-card__subtitle, .job-card-container__company-name")
                    link_el    = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
                    loc_el     = card.select_one(".job-search-card__location")

                    title   = title_el.get_text(strip=True)   if title_el   else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    loc     = loc_el.get_text(strip=True)     if loc_el     else location
                    href    = link_el["href"].split("?")[0]   if link_el    else ""

                    if not title or not href:
                        continue
                    if is_senior(title):
                        continue

                    jid = job_id(href, title, company)
                    if jid in seen:
                        continue

                    results.append({
                        "id": jid,
                        "source": "linkedin",
                        "title": title,
                        "company": company,
                        "location": loc,
                        "url": href,
                        "description": "",
                        "scraped_at": datetime.now().isoformat(),
                        "applied": False,
                        "status": "new"
                    })
                    seen.add(jid)

                except Exception as e:
                    log.debug(f"LinkedIn card parse error: {e}")
                    continue

            human_delay(1.5, 3)

        except Exception as e:
            log.warning(f"LinkedIn public '{keywords}' failed: {e}")
            continue

    results = fetch_linkedin_descriptions(results, session)
    log.info(f"LinkedIn public: {len(results)} jobs")
    return results[:limit]


def fetch_linkedin_descriptions(jobs, session):
    """Fetch job descriptions from LinkedIn public job pages."""
    for job in jobs:
        if job.get("description"):
            continue
        try:
            resp = session.get(job["url"], timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                desc_el = soup.select_one(
                    "div.show-more-less-html__markup, "
                    "div.description__text, "
                    "section.description"
                )
                if desc_el:
                    job["description"] = desc_el.get_text(" ", strip=True)[:2500]
            human_delay(0.5, 1.2)
        except Exception:
            pass
    return jobs


# ── 3. Wellfound (public listings page) ───────────────────────────────────
def scrape_wellfound(seen, profile, limit=10):
    log.info("Scraping Wellfound...")
    results = []

    # Wellfound uses NYC slug regardless of location (startup hub)
    urls = [
        "https://wellfound.com/jobs?role=intern&locationSlugs%5B%5D=new-york-city",
        "https://wellfound.com/jobs?q=intern&locationSlugs%5B%5D=new-york-city&remote=false",
    ]

    session = requests.Session()
    session.headers.update(HEADERS)

    for url in urls:
        if len(results) >= limit:
            break
        try:
            resp = session.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = soup.select("div[class*='styles_jobListing'], div[class*='JobListing']")
            if not cards:
                cards = soup.select("a[href*='/jobs/']")

            log.info(f"Wellfound: {len(cards)} raw cards from {url}")

            for card in cards[:15]:
                try:
                    title_el   = card.select_one("h2, h3, [class*='title'], [class*='role']")
                    company_el = card.select_one("[class*='company'], [class*='startup'], [class*='name']")
                    link_el    = card if card.name == "a" else card.select_one("a[href*='/jobs/']")

                    title   = title_el.get_text(strip=True)   if title_el   else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    href    = (link_el.get("href") or "")     if link_el    else ""
                    url_full = f"https://wellfound.com{href}" if href.startswith("/") else href

                    if not title or not url_full:
                        continue
                    if is_senior(title):
                        continue

                    jid = job_id(url_full, title, company)
                    if jid in seen:
                        continue

                    results.append({
                        "id": jid,
                        "source": "wellfound",
                        "title": title,
                        "company": company,
                        "location": profile.get("location_preference", "New York, NY"),
                        "url": url_full,
                        "description": "",
                        "scraped_at": datetime.now().isoformat(),
                        "applied": False,
                        "status": "new"
                    })
                    seen.add(jid)

                except Exception:
                    continue

            human_delay(1, 2)

        except Exception as e:
            log.warning(f"Wellfound failed: {e}")

    log.info(f"Wellfound: {len(results)} jobs")
    return results[:limit]


# ── 4. Handshake public search ─────────────────────────────────────────────
def scrape_handshake_public(seen, profile, limit=10):
    """Use Handshake's public-facing job search (no login needed for browsing)."""
    log.info("Scraping Handshake (public)...")
    results = []
    loc_param = requests.utils.quote(profile.get("location_preference", "New York, NY"))

    session = requests.Session()
    session.headers.update(HEADERS)

    search_urls = [
        f"https://joinhandshake.com/career-advice/jobs/?page=1&category=internship&location={loc_param}",
        f"https://app.joinhandshake.com/postings?page=1&per_page=25&sort_direction=desc&sort_column=created_at&job_type_names[]=Internship&employment_type_names[]=Paid&location={loc_param}",
    ]

    for url in search_urls:
        if len(results) >= limit:
            break
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                log.warning(f"Handshake public: {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(
                "li[class*='style__list-item'], div[class*='job-listing'], "
                "article[class*='job'], div[class*='JobCard'], div[class*='posting']"
            )
            log.info(f"Handshake: {len(cards)} cards")

            for card in cards[:20]:
                try:
                    title_el   = card.select_one("h3, h2, [class*='title'], strong")
                    company_el = card.select_one("[class*='employer'], [class*='company'], [class*='org']")
                    link_el    = card.select_one("a")

                    title   = title_el.get_text(strip=True)   if title_el   else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    href    = (link_el.get("href") or "")     if link_el    else ""
                    url_full = f"https://app.joinhandshake.com{href}" if href.startswith("/") else href

                    if not title or not url_full:
                        continue
                    if is_senior(title):
                        continue

                    jid = job_id(url_full, title, company)
                    if jid in seen:
                        continue

                    results.append({
                        "id": jid,
                        "source": "handshake",
                        "title": title,
                        "company": company,
                        "location": profile.get("location_preference", ""),
                        "url": url_full,
                        "description": "",
                        "scraped_at": datetime.now().isoformat(),
                        "applied": False,
                        "status": "new"
                    })
                    seen.add(jid)

                except Exception:
                    continue

            human_delay(1, 2)

        except Exception as e:
            log.warning(f"Handshake public failed: {e}")

    log.info(f"Handshake: {len(results)} jobs")
    return results[:limit]


# ── 5. Internships.com ─────────────────────────────────────────────────────
def scrape_internships_dot_com(seen, profile, limit=10):
    log.info("Scraping Internships.com...")
    results = []
    loc_param = requests.utils.quote(profile.get("location_preference", "New York, NY"))
    year_tag = ""
    if profile.get("availability_start"):
        year_tag = profile["availability_start"][:4]

    session = requests.Session()
    session.headers.update(HEADERS)

    base_q = f"summer+{year_tag}" if year_tag else "summer+intern"
    urls = [
        f"https://www.internships.com/app/search?q={base_q}&l={loc_param}&paid=true",
        f"https://www.internships.com/app/search?q=marketing+intern&l={loc_param}",
        f"https://www.internships.com/app/search?q=business+intern&l={loc_param}",
    ]

    for url in urls:
        if len(results) >= limit:
            break
        try:
            resp = session.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(
                "div[class*='InternshipCard'], div[class*='JobCard'], "
                "article[class*='internship'], li[class*='result']"
            )
            if not cards:
                cards = soup.select("a[href*='/internship/']")
            log.info(f"Internships.com: {len(cards)} cards from {url}")

            for card in cards[:15]:
                try:
                    title_el   = card.select_one("h2, h3, [class*='title']")
                    company_el = card.select_one("[class*='company'], [class*='employer']")
                    link_el    = card if card.name == "a" else card.select_one("a")

                    title   = title_el.get_text(strip=True)   if title_el   else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    href    = (link_el.get("href") or "")     if link_el    else ""
                    url_full = f"https://www.internships.com{href}" if href.startswith("/") else href

                    if not title or not url_full:
                        continue
                    if is_senior(title):
                        continue

                    jid = job_id(url_full, title, company)
                    if jid in seen:
                        continue

                    results.append({
                        "id": jid,
                        "source": "internships.com",
                        "title": title,
                        "company": company,
                        "location": profile.get("location_preference", ""),
                        "url": url_full,
                        "description": "",
                        "scraped_at": datetime.now().isoformat(),
                        "applied": False,
                        "status": "new"
                    })
                    seen.add(jid)

                except Exception:
                    continue

            human_delay(1, 2)

        except Exception as e:
            log.warning(f"Internships.com failed: {e}")

    log.info(f"Internships.com: {len(results)} jobs")
    return results[:limit]


# ── 6. SimplyHired ─────────────────────────────────────────────────────────
def scrape_simplyhired(seen, profile, limit=10):
    log.info("Scraping SimplyHired...")
    results = []
    loc_param = profile.get("location_preference", "New York, NY")
    year_tag = ""
    if profile.get("availability_start"):
        year_tag = profile["availability_start"][:4]

    session = requests.Session()
    session.headers.update(HEADERS)

    queries_raw = [
        f"summer {year_tag} intern" if year_tag else "summer intern",
        f"paid internship {year_tag}" if year_tag else "paid internship",
        "startup intern",
    ]

    for q in queries_raw:
        if len(results) >= limit:
            break
        try:
            url = (
                f"https://www.simplyhired.com/search"
                f"?q={requests.utils.quote(q)}"
                f"&l={requests.utils.quote(loc_param)}"
                f"&fdb=14"
            )
            resp = session.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = soup.select(
                "div[data-testid='searchSerpJob'], "
                "article.SerpJob, div.SerpJob-jobCard, "
                "li[class*='jobposting']"
            )
            log.info(f"SimplyHired '{q}': {len(cards)} cards")

            for card in cards[:10]:
                try:
                    title_el   = card.select_one("h2, h3, [data-testid='searchSerpJobTitle'], a[class*='chakra-button']")
                    company_el = card.select_one("[data-testid='searchSerpCompanyName'], span[class*='company']")
                    link_el    = card.select_one("a[href*='/job/'], a[href*='/jobs/']")

                    title   = title_el.get_text(strip=True)   if title_el   else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    href    = (link_el.get("href") or "")     if link_el    else ""
                    url_full = f"https://www.simplyhired.com{href}" if href.startswith("/") else href

                    if not title or not url_full:
                        continue
                    if is_senior(title):
                        continue

                    jid = job_id(url_full, title, company)
                    if jid in seen:
                        continue

                    results.append({
                        "id": jid,
                        "source": "simplyhired",
                        "title": title,
                        "company": company,
                        "location": loc_param,
                        "url": url_full,
                        "description": "",
                        "scraped_at": datetime.now().isoformat(),
                        "applied": False,
                        "status": "new"
                    })
                    seen.add(jid)

                except Exception:
                    continue

            human_delay(1, 2)

        except Exception as e:
            log.warning(f"SimplyHired '{q}' failed: {e}")

    log.info(f"SimplyHired: {len(results)} jobs")
    return results[:limit]


# ── Main orchestrator ──────────────────────────────────────────────────────
def run_scraper(target=40):
    profile = load_profile()
    seen = load_seen()  # Persistent across days — never re-scrapes the same job
    all_jobs = []

    scrapers = [
        (scrape_indeed_rss,          20),
        (scrape_linkedin_public,     20),
        (scrape_simplyhired,         10),
        (scrape_wellfound,           10),
        (scrape_handshake_public,    10),
        (scrape_internships_dot_com, 10),
    ]

    for scraper_fn, lim in scrapers:
        try:
            jobs = scraper_fn(seen, profile, limit=lim)
            all_jobs.extend(jobs)
            log.info(f"Running total: {len(all_jobs)} jobs")
        except Exception as e:
            log.error(f"Scraper {scraper_fn.__name__} crashed: {e}")
        if len(all_jobs) >= target:
            break

    save_seen(seen)  # Persist seen IDs so tomorrow's run skips today's jobs

    if all_jobs:
        atomic_write(TODAY_FILE, json.dumps(all_jobs, indent=2))
        log.info(f"Saved {len(all_jobs)} jobs to {TODAY_FILE}")
    else:
        log.warning("No jobs found — all sources returned 0 results")

    return all_jobs


if __name__ == "__main__":
    jobs = run_scraper()
    print(f"\n✅ Scraped {len(jobs)} new jobs")
    for j in jobs[:10]:
        print(f"  [{j['source']:15}] {j['title'][:45]:45} @ {j['company'][:30]}")
