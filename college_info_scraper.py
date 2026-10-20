#!/usr/bin/env python3
"""
College info + placement scraper. Reads college_master.csv (from
build_college_list.py), finds each college's official website if not
already known, crawls it, and saves one JSON per college.

Setup:
    pip install requests beautifulsoup4

Run:
    python college_info_scraper.py --colleges college_master.csv --out ./college_info

HONESTY UP FRONT - read this before trusting the output:
- URL discovery uses DuckDuckGo's HTML search (no API key needed), but it is
  NOT reliable: it can be rate-limited, blocked, or return a wrong/outdated
  link, especially for colleges with generic names. Every auto-found URL is
  saved with "url_source": "auto_search" so you know to spot-check it - a
  college-code -> official-URL list from DTE Maharashtra or AICTE's facility
  list would be far more reliable input than search, if you can get one.
- Placement/NAAC/fee figures are pulled out of scraped page text with
  regex pattern-matching, not real understanding of the page. This WILL
  miscapture numbers sometimes (e.g. a rupee figure that's actually a fee,
  not a placement package). Every extracted figure is kept next to the raw
  sentence it came from ("context") so a human or a downstream LLM pass can
  verify it - never feed these numbers into a user-facing answer without
  that review step, per this project's own stated data policy.
- This script is built to run from a machine with open internet access and
  was not tested from this sandboxed environment, which cannot reach
  arbitrary college/search domains. Run it locally, start with
  --limit 5 first, and check the output before a full run.

Output: one JSON per college at out/<institute_code>_<slug>.json, e.g.:
{
  "institute_code": "1002",
  "institute_name": "...",
  "url": "https://...",
  "url_source": "auto_search" | "provided",
  "scraped_at": "...",
  "pages_crawled": [...],
  "extracted": {
    "naac_grade": {"value": "A+", "context": "...sentence it was found in...", "confidence": "heuristic"},
    "established_year": {...},
    "affiliation": {...},
    "contact": {"emails": [...], "phones": [...]},
    "placement_mentions": [
      {"value": "92%", "kind": "placement_rate", "context": "...", "source_page": "...", "confidence": "heuristic"},
      {"value": "₹12,00,000", "kind": "package_rupees", "context": "...", "source_page": "...", "confidence": "heuristic"}
    ]
  },
  "raw_text_pages": {"https://...": "full extracted page text, for a later LLM extraction pass"}
}
"""
import argparse, csv, hashlib, json, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = "AdmissionEvidenceBot/0.2 (research; contact: your-email@example.com)"
HEADERS = {"User-Agent": UA}
PRIORITY_KEYWORDS = {
    "placement": 6, "placements": 6, "training and placement": 6, "tpo": 5,
    "about": 2, "naac": 5, "nirf": 5, "nba": 4, "accreditation": 4,
    "fee": 4, "fees": 4, "admission": 3, "hostel": 3, "infrastructure": 2,
    "mandatory disclosure": 5, "contact": 2,
}
MAX_PAGES_PER_COLLEGE = 25
CRAWL_DELAY = 2.0  # seconds between requests to the SAME site


def ddg_search_url(query):
    """DuckDuckGo's HTML-only endpoint - no API key, but fragile/rate-limited."""
    import urllib.parse as up
    return "https://html.duckduckgo.com/html/?q=" + up.quote(query)


def find_official_site(college_name, session):
    try:
        r = session.get(ddg_search_url(f"{college_name} official website"),
                        headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a.result__a, a.result__url")[:5]:
            href = a.get("href", "")
            if href.startswith("http") and not any(
                bad in href for bad in ["facebook.com", "wikipedia.org", "youtube.com",
                                        "instagram.com", "linkedin.com", "shiksha.com",
                                        "collegedunia.com", "careers360.com"]):
                return href
    except Exception as e:
        print(f"  search failed for {college_name}: {e}")
    return None


RE_NAAC = re.compile(r"NAAC[^.]{0,80}?\b([A-D][+\-]{0,2}|Grade\s*[A-D])\b", re.I)
RE_YEAR = re.compile(r"(?:established|founded|since)\D{0,10}(1[89]\d{2}|20[0-2]\d)", re.I)
RE_AFFIL = re.compile(r"affiliated\s+to\s+([A-Z][^.]{5,80})", re.I)
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RE_PHONE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}|\d{3,5}[-\s]\d{6,8}")
RE_PLACEMENT_RATE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%[^.]{0,40}?(?:placed|placement)", re.I)
RE_PACKAGE = re.compile(r"(?:₹|rs\.?|inr)\s?([\d,]+(?:\.\d+)?)\s*(lakh|lpa|lac|crore)?", re.I)


def extract_context(text, match_start, match_end, pad=60):
    return text[max(0, match_start - pad):match_end + pad].replace("\n", " ").strip()


def extract_fields(pages_text):
    """pages_text: {url: text}. Returns the 'extracted' dict, heuristic throughout."""
    out = {"naac_grade": None, "established_year": None, "affiliation": None,
           "contact": {"emails": [], "phones": []}, "placement_mentions": []}
    emails, phones = set(), set()
    for url, text in pages_text.items():
        if not out["naac_grade"]:
            m = RE_NAAC.search(text)
            if m:
                out["naac_grade"] = {"value": m.group(1), "context": extract_context(text, *m.span()),
                                     "source_page": url, "confidence": "heuristic"}
        if not out["established_year"]:
            m = RE_YEAR.search(text)
            if m:
                out["established_year"] = {"value": m.group(1), "context": extract_context(text, *m.span()),
                                           "source_page": url, "confidence": "heuristic"}
        if not out["affiliation"]:
            m = RE_AFFIL.search(text)
            if m:
                out["affiliation"] = {"value": m.group(1).strip(), "context": extract_context(text, *m.span()),
                                      "source_page": url, "confidence": "heuristic"}
        emails.update(RE_EMAIL.findall(text))
        phones.update(RE_PHONE.findall(text))
        for m in RE_PLACEMENT_RATE.finditer(text):
            out["placement_mentions"].append({"value": m.group(1) + "%", "kind": "placement_rate",
                                               "context": extract_context(text, *m.span()),
                                               "source_page": url, "confidence": "heuristic"})
        for m in RE_PACKAGE.finditer(text):
            ctx = extract_context(text, *m.span())
            if "placement" in ctx.lower() or "package" in ctx.lower() or "ctc" in ctx.lower():
                out["placement_mentions"].append({"value": m.group(0).strip(), "kind": "package_rupees",
                                                   "context": ctx, "source_page": url, "confidence": "heuristic"})
    out["contact"]["emails"] = sorted(emails)[:10]
    out["contact"]["phones"] = sorted(phones)[:10]
    # cap placement mentions and de-dup near-identical contexts
    seen, dedup = set(), []
    for m in out["placement_mentions"]:
        key = m["context"][:50]
        if key not in seen:
            seen.add(key)
            dedup.append(m)
    out["placement_mentions"] = dedup[:30]
    return out


def score(url, anchor_text):
    s = (url + " " + anchor_text).lower()
    return sum(w for k, w in PRIORITY_KEYWORDS.items() if k in s)


def crawl_college(url, session):
    """Breadth-first-ish priority crawl of one site. Returns {url: text}."""
    import heapq
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    heap = [(0, url)]
    seen = {url}
    pages = {}
    last_hit = 0.0
    while heap and len(pages) < MAX_PAGES_PER_COLLEGE:
        _, u = heapq.heappop(heap)
        wait = CRAWL_DELAY - (time.time() - last_hit)
        if wait > 0:
            time.sleep(wait)
        last_hit = time.time()
        try:
            r = session.get(u, headers=HEADERS, timeout=20)
            if "html" not in r.headers.get("content-type", "").lower():
                continue
            soup = BeautifulSoup(r.content, "html.parser")
            text = soup.get_text(" ", strip=True)
            pages[u] = text
            for a in soup.find_all("a", href=True):
                link = urljoin(u, a["href"]).split("#")[0]
                if link in seen or urlparse(link).netloc.lower().removeprefix("www.") != domain:
                    continue
                seen.add(link)
                heapq.heappush(heap, (-score(link, a.get_text(" ")), link))
        except Exception as e:
            pages[u] = ""
    return pages


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", (s or "college").lower()).strip("_")[:60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--colleges", required=True, help="college_master.csv from build_college_list.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="only process the first N colleges (0 = all)")
    ap.add_argument("--resume", action="store_true", help="skip colleges whose output file already exists")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    with open(args.colleges, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[:args.limit]

    for i, row in enumerate(rows, 1):
        code, name = row["institute_code"], row["institute_name"]
        out_file = out / f"{code}_{slug(name)}.json"
        if args.resume and out_file.exists():
            continue
        print(f"[{i}/{len(rows)}] {code} {name}")

        url, url_source = (row.get("url") or "").strip(), "provided"
        if not url:
            url = find_official_site(name, session)
            url_source = "auto_search"
            time.sleep(1.5)  # be polite to the search endpoint too
        if not url:
            result = {"institute_code": code, "institute_name": name, "url": None,
                      "url_source": None, "scraped_at": datetime.now(timezone.utc).isoformat(),
                      "error": "no official site found"}
            out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            continue

        pages = crawl_college(url, session)
        extracted = extract_fields(pages)
        result = {
            "institute_code": code, "institute_name": name,
            "url": url, "url_source": url_source,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "pages_crawled": list(pages.keys()),
            "extracted": extracted,
            "raw_text_pages": pages,  # kept for a later proper LLM extraction pass
        }
        out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nDone. Output in {out}/")
    print("Next step: run an LLM pass over raw_text_pages for each college to replace the regex-based "
          "'extracted' block with something you can actually trust for placement figures.")


if __name__ == "__main__":
    main()
