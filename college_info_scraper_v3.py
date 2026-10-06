#!/usr/bin/env python3
"""
AI-Con College Information Scraper v3

Input:
  college_master.csv produced by build_college_list.py

Output:
  scraper_output/
    <institute_code>_<slug>.json
    scrape_summary.csv
    needs_url.csv
    failed.csv
    run_metadata.json
    pdfs/<college_code>/... (when --save-pdfs is used)

Features:
  - one college or all colleges
  - optional URL discovery (DuckDuckGo then Bing, bounded timeouts)
  - controlled parallelism across colleges
  - --resume support
  - same-domain priority crawler
  - linked PDF discovery + PyMuPDF text extraction
  - evidence with source URL, source type, context, and years mentioned
  - placement/package extraction including LPA formats such as 7.00 LPA
  - historical evidence indexing for 2020-2025 by default
  - unresolved URLs are recorded instead of blocking the whole run

Install:
  pip install requests beautifulsoup4 pymupdf

Examples:
  # One college, safest first test:
  python3 college_info_scraper_v3.py \\
      --colleges ./V4_daataa/college_master.csv \\
      --college-code 01012 \\
      --url https://www.gcoey.ac.in/ \\
      --out ./scraper_output \\
      --save-pdfs

  # All colleges where URL is already present in CSV:
  python3 college_info_scraper_v3.py \\
      --colleges ./V4_daataa/college_master.csv \\
      --out ./scraper_output \\
      --workers 6 \\
      --resume

  # All colleges and bounded automatic URL discovery:
  python3 college_info_scraper_v3.py \\
      --colleges ./V4_daataa/college_master.csv \\
      --out ./scraper_output \\
      --workers 6 \\
      --discover \\
      --resume

Important:
  This is an evidence collector, not a guarantee that every fact exists.
  It does not invent missing historical values. Verify important figures
  against the source URL/context before using them in user-facing answers.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import pymupdf
except ImportError:
    pymupdf = None

VERSION = "3.0-evidence-first"
USER_AGENT = "AI-Con-CollegeEvidenceBot/3.0 (educational research)"

BAD_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com",
    "wikipedia.org", "shiksha.com", "collegedunia.com", "careers360.com",
    "collegedekho.com", "getmyuni.com", "zollege.in", "collegebatch.com",
    "targetadmission.com", "justdial.com", "mappls.com", "google.com",
    "bing.com", "duckduckgo.com",
}

PRIORITY = {
    "placement": 14, "placements": 14, "training and placement": 15,
    "tpo": 10, "career": 8, "recruiter": 10, "recruiters": 10,
    "nirf": 11, "mandatory disclosure": 14, "disclosure": 7,
    "naac": 10, "nba": 10, "accreditation": 9, "annual report": 10,
    "report": 4, "iqac": 8, "admission": 7, "admissions": 7,
    "fee": 7, "fees": 7, "scholarship": 7, "hostel": 5,
    "infrastructure": 4, "facilities": 4, "contact": 4, "about": 3,
    "approval": 8, "aicte": 8, "university": 4, "department": 3,
    "faculty": 3, "ranking": 7, "achievement": 6, "alumni": 3,
}

PDF_HINTS = (
    "placement", "nirf", "mandatory", "disclosure", "annual", "report",
    "accredit", "naac", "nba", "fee", "admission", "brochure",
    "prospectus", "iqac", "approval", "recruit", "scholar",
)

SKIP_HINTS = (
    "javascript:", "mailto:", "tel:", "#", "login", "logout",
    "signin", "signup", "captcha",
)

YEAR_RANGE_RE = re.compile(r"\b((?:19|20)\d{2})\s*[-/–]\s*((?:19|20)?\d{2})\b")
YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}|\d{3,5}[-\s]\d{6,8}")

NAAC_RE = re.compile(r"\bNAAC\b[^.\n]{0,140}?\b(A\+\+|A\+|A-|A|B\+\+|B\+|B-|B|C|D)\b", re.I)
ESTABLISHED_RE = re.compile(r"\b(?:established|founded|since)\D{0,25}((?:18|19|20)\d{2})\b", re.I)
AFFIL_RE = re.compile(r"\b(?:affiliated|affiliation)\s*(?:to|with|:)?\s*([A-Z][^.]{10,180})", re.I)
PLACEMENT_RATE_RE = re.compile(r"(?P<value>\d{1,3}(?:\.\d+)?)\s*%[^.\n]{0,100}(?:placed|placement|placements|students placed|employed)", re.I)
LPA_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:LPA|LAKH(?:S)?\s*PER\s*ANNUM|LAC|LAKHS?)\b", re.I)
CRORE_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:CRORE|CR)\b", re.I)
RUPEE_RE = re.compile(r"(?P<value>(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?)", re.I)
PACKAGE_LABEL_RE = re.compile(r"\b(highest package|average package|avg package|median package|lowest package|salary package|ctc|package)\b[^.\n]{0,180}", re.I)
MEDIAN_RE = re.compile(r"\bmedian\s+(?:salary|package|ctc)?\D{0,40}((?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?)", re.I)
FEE_RE = re.compile(r"\b(?:annual\s+)?(?:tuition\s+)?fees?\b[^.\n]{0,120}((?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?)", re.I)
RECRUITER_RE = re.compile(r"\b(?:recruiters?|recruitment partners?|hiring partners?)\b[^.\n]{0,300}", re.I)
ADMISSION_RE = re.compile(r"\b(admission|admissions|eligibility|entrance|cut.?off|counselling)\b[^.\n]{0,200}", re.I)
APPROVAL_RE = re.compile(r"\b(AICTE|UGC|DTE|CET Cell|NBA|NAAC|autonomous|approval|approved)\b[^.\n]{0,220}", re.I)
RANKING_RE = re.compile(r"\b(NIRF|ranking|ranked|rank)\b[^.\n]{0,200}", re.I)
CONTACT_CONTEXT_RE = re.compile(r"\b(contact|phone|email|address|office|principal|registrar)\b[^.\n]{0,220}", re.I)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def slug(value):
    value = re.sub(r"[^a-z0-9]+", "_", (value or "college").lower())
    return value.strip("_")[:75] or "college"


def normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    url, _ = urldefrag(url)
    return url.rstrip("/")


def domain(url):
    return urlparse(url).netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")


def is_bad_domain(url):
    d = domain(url)
    return any(d == x or d.endswith("." + x) for x in BAD_DOMAINS)


def same_domain(a, b):
    return domain(a) == domain(b)


def context(text, start, end, pad=180):
    lo, hi = max(0, start - pad), min(len(text), end + pad)
    return re.sub(r"\s+", " ", text[lo:hi]).strip()


def parse_years(text, wanted):
    found = set()
    for m in YEAR_RANGE_RE.finditer(text):
        a = int(m.group(1))
        raw_b = m.group(2)
        b = (a // 100) * 100 + int(raw_b) if len(raw_b) == 2 else int(raw_b)
        labels = {str(a), str(b), f"{a}-{b % 100:02d}"}
        if not wanted or any(any(y in label for label in labels) for y in wanted):
            found.add(f"{a}-{b % 100:02d}")
    for m in YEAR_RE.finditer(text):
        if not wanted or m.group(1) in wanted:
            found.add(m.group(1))
    return sorted(found)


def evidence(value, kind, text, match, source_url, source_type, wanted):
    ctx = context(text, *match)
    return {
        "value": value,
        "kind": kind,
        "context": ctx,
        "source_url": source_url,
        "source_type": source_type,
        "years_mentioned": parse_years(ctx, wanted),
        "confidence": "heuristic",
    }


def make_session():
    s = requests.Session()
    retry = Retry(
        total=1,
        connect=1,
        read=1,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=6, pool_maxsize=6)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.7",
    })
    return s


def search_candidates(name, session, timeout):
    import urllib.parse as up
    q = up.quote(f'"{name}" Maharashtra official website')
    searchers = [
        ("duckduckgo", f"https://html.duckduckgo.com/html/?q={q}"),
        ("bing", f"https://www.bing.com/search?q={q}"),
    ]
    for backend, url in searchers:
        try:
            r = session.get(url, timeout=(2.5, timeout), headers={"User-Agent": USER_AGENT})
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            links = []
            selectors = ["a.result__a", "a.result__url"] if backend == "duckduckgo" else ["li.b_algo h2 a"]
            for sel in selectors:
                for a in soup.select(sel)[:10]:
                    href = a.get("href", "")
                    if "uddg=" in href:
                        vals = parse_qs(urlparse(href).query).get("uddg")
                        if vals:
                            href = unquote(vals[0])
                    href = normalize_url(href)
                    if href.startswith("http") and not is_bad_domain(href):
                        links.append(href)
            links = list(dict.fromkeys(links))
            if links:
                scored = sorted(links, key=lambda u: (
                    20 if ".ac.in" in u.lower() else 0
                    + sum(v for k, v in PRIORITY.items() if k in u.lower())
                ), reverse=True)
                return scored[:8], backend
        except requests.RequestException:
            continue
    return [], None


def discover_site(name, session, timeout):
    candidates, backend = search_candidates(name, session, timeout)
    for candidate in candidates:
        try:
            r = session.get(candidate, timeout=(2.5, timeout), allow_redirects=True)
            if r.ok and "html" in r.headers.get("content-type", "").lower():
                final = normalize_url(r.url)
                if final and not is_bad_domain(final):
                    return final, f"auto_search_{backend}"
        except requests.RequestException:
            continue
    return None, None


def link_score(url, anchor=""):
    s = f"{url} {anchor}".lower()
    return sum(weight for key, weight in PRIORITY.items() if key in s)


def is_pdf(url, anchor="", content_type=""):
    s = f"{url} {anchor}".lower()
    return "application/pdf" in (content_type or "").lower() or ".pdf" in s


def clean_text(soup):
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:350_000]


def crawl_site(root_url, session, args, save_pdf_dir=None):
    heap = [(-1000, 0, root_url)]
    queued = {root_url}
    pages, documents, errors = {}, [], []
    seq, last_hit = 1, 0.0

    while heap and len(pages) < args.max_pages:
        _, _, url = heapq.heappop(heap)
        if url in pages or is_bad_domain(url):
            continue

        wait = args.delay - (time.time() - last_hit)
        if wait > 0:
            time.sleep(wait)

        try:
            r = session.get(url, timeout=(3, args.timeout), allow_redirects=True)
            last_hit = time.time()
        except requests.RequestException as exc:
            last_hit = time.time()
            errors.append({"url": url, "error": str(exc)[:250]})
            continue

        if r.status_code >= 400:
            errors.append({"url": url, "error": f"http_{r.status_code}"})
            continue

        final_url = normalize_url(r.url)
        ctype = r.headers.get("content-type", "").lower()

        if is_pdf(final_url, content_type=ctype):
            if len(documents) >= args.max_pdfs:
                continue
            doc = {
                "url": final_url,
                "title": Path(urlparse(final_url).path).name,
                "source_type": "pdf",
                "pages": 0,
                "text": "",
                "text_available": False,
                "error": None,
            }
            try:
                data = r.content
                if save_pdf_dir:
                    save_pdf_dir.mkdir(parents=True, exist_ok=True)
                    fname = slug(Path(urlparse(final_url).path).stem) + ".pdf"
                    target = save_pdf_dir / fname
                    n = 2
                    while target.exists():
                        target = save_pdf_dir / f"{Path(fname).stem}_{n}.pdf"
                        n += 1
                    target.write_bytes(data)
                    doc["local_file"] = str(target)
                if pymupdf is None:
                    doc["error"] = "PyMuPDF is not installed"
                else:
                    pdf = pymupdf.open(stream=data, filetype="pdf")
                    doc["pages"] = len(pdf)
                    chunks = [pdf.load_page(i).get_text("text") for i in range(min(len(pdf), args.max_pdf_pages))]
                    doc["text"] = re.sub(r"\s+", " ", " ".join(chunks))[:350_000]
                    doc["text_available"] = bool(doc["text"])
                    pdf.close()
            except Exception as exc:
                doc["error"] = str(exc)[:250]
            documents.append(doc)
            continue

        if "html" not in ctype:
            continue

        soup = BeautifulSoup(r.content, "html.parser")
        pages[final_url] = clean_text(soup)

        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or any(href.lower().startswith(x) for x in SKIP_HINTS):
                continue
            link = normalize_url(urljoin(final_url, href))
            if not link or link in queued or is_bad_domain(link):
                continue
            anchor = a.get_text(" ", strip=True)
            if is_pdf(link, anchor):
                if len(documents) < args.max_pdfs:
                    heapq.heappush(heap, (-2000, seq, link))
                    queued.add(link)
                    seq += 1
                continue
            if not same_domain(root_url, link):
                continue
            path = urlparse(link).path.lower()
            if any(x in path for x in ("/wp-admin", "/login", "/cart", "/feed")):
                continue
            heapq.heappush(heap, (-link_score(link, anchor), seq, link))
            queued.add(link)
            seq += 1

    return pages, documents, errors


def extract_information(pages, documents, wanted):
    sources = [(u, "html", t) for u, t in pages.items()]
    sources += [(d["url"], "pdf", d.get("text", "")) for d in documents if d.get("text_available")]

    out = {
        "naac": [], "nba": [], "nirf": [], "established_year": [],
        "affiliation": [], "fees": [], "placement_mentions": [],
        "recruiter_mentions": [], "admission_mentions": [],
        "approval_mentions": [], "ranking_mentions": [], "contact_mentions": [],
        "contact": {"emails": [], "phones": []},
    }
    emails, phones, seen = set(), set(), set()
    historical = {}

    def add(bucket, item):
        key = (bucket, item["value"], item["source_url"], item["context"][:100])
        if key not in seen:
            seen.add(key)
            out[bucket].append(item)

    pattern_specs = [
        (NAAC_RE, "naac", "naac_grade"),
        (ESTABLISHED_RE, "established_year", "established_year"),
        (AFFIL_RE, "affiliation", "affiliation"),
        (RECRUITER_RE, "recruiter_mentions", "recruiter_mention"),
        (ADMISSION_RE, "admission_mentions", "admission_mention"),
        (APPROVAL_RE, "approval_mentions", "approval_mention"),
        (RANKING_RE, "ranking_mentions", "ranking_mention"),
        (CONTACT_CONTEXT_RE, "contact_mentions", "contact_mention"),
    ]

    for source_url, source_type, text in sources:
        if not text:
            continue
        emails.update(EMAIL_RE.findall(text))
        phones.update(PHONE_RE.findall(text))

        for regex, bucket, kind in pattern_specs:
            for m in regex.finditer(text):
                value = m.group(1) if m.lastindex == 1 else m.group(0)
                add(bucket, evidence(value.strip(), kind, text, m.span(), source_url, source_type, wanted))

        for m in PLACEMENT_RATE_RE.finditer(text):
            add("placement_mentions", evidence(m.group("value") + "%", "placement_rate", text, m.span(), source_url, source_type, wanted))

        for m in LPA_RE.finditer(text):
            ctx = context(text, *m.span())
            if any(k in ctx.lower() for k in ("placement", "package", "ctc", "salary", "recruit", "selected")):
                add("placement_mentions", evidence(m.group(0).strip(), "package_lpa", text, m.span(), source_url, source_type, wanted))

        for m in CRORE_RE.finditer(text):
            ctx = context(text, *m.span())
            if any(k in ctx.lower() for k in ("placement", "package", "ctc", "salary")):
                add("placement_mentions", evidence(m.group(0).strip(), "package_crore", text, m.span(), source_url, source_type, wanted))

        for m in RUPEE_RE.finditer(text):
            ctx = context(text, *m.span())
            low = ctx.lower()
            if any(k in low for k in ("placement", "package", "ctc", "salary")):
                add("placement_mentions", evidence(m.group(0).strip(), "placement_rupees", text, m.span(), source_url, source_type, wanted))
            elif "fee" in low or "fees" in low:
                add("fees", evidence(m.group(0).strip(), "fee_rupees", text, m.span(), source_url, source_type, wanted))

        for m in MEDIAN_RE.finditer(text):
            add("placement_mentions", evidence(m.group(1).strip(), "median_salary_or_package", text, m.span(), source_url, source_type, wanted))

        for m in PACKAGE_LABEL_RE.finditer(text):
            add("placement_mentions", evidence(m.group(1), "package_label", text, m.span(), source_url, source_type, wanted))

        for m in FEE_RE.finditer(text):
            add("fees", evidence(m.group(1).strip(), "fee_rupees", text, m.span(), source_url, source_type, wanted))

    out["contact"]["emails"] = sorted(emails)[:30]
    out["contact"]["phones"] = sorted(phones)[:30]

    for bucket in ("placement_mentions", "fees", "nirf", "naac", "nba", "recruiter_mentions", "ranking_mentions", "approval_mentions"):
        for item in out[bucket]:
            for year in item.get("years_mentioned", []):
                historical.setdefault(year, {}).setdefault(bucket, []).append(item)

    return out, historical


def load_rows(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def select_rows(rows, code, limit):
    if code:
        found = [r for r in rows if r.get("institute_code") == code]
        if not found:
            raise SystemExit(f"Institute code {code!r} was not found in the CSV.")
        return found[:1]
    return rows[:limit] if limit else rows


def scrape_one(row, args):
    code = (row.get("institute_code") or "").strip()
    name = (row.get("institute_name") or "").strip()
    outfile = args.out / f"{code}_{slug(name)}.json"

    if args.resume and outfile.exists():
        return {"institute_code": code, "institute_name": name, "url": "", "url_source": "resume_skip", "pages_crawled": "", "pdfs_found": "", "placement_mentions": "", "historical_years": "", "errors": "", "status": "skipped"}

    session = make_session()
    if args.url and args.college_code == code:
        url, url_source = normalize_url(args.url), "provided_cli"
    else:
        url = normalize_url(row.get("url") or "")
        url_source = "provided_csv" if url else None

    if not url and args.discover:
        url, url_source = discover_site(name, session, args.search_timeout)

    result = {
        "schema_version": VERSION,
        "institute_code": code,
        "institute_name": name,
        "url": url,
        "url_source": url_source,
        "scraped_at": now_iso(),
        "requested_history_years": sorted(args.wanted_years),
        "crawl": {"max_pages": args.max_pages, "max_pdfs": args.max_pdfs, "delay_seconds": args.delay, "pages_crawled": [], "pdf_count": 0, "errors": []},
        "extracted": None,
        "historical": {},
        "documents": [],
    }

    if not url:
        result["status"] = "needs_url"
        result["message"] = "No official URL available. Add url to CSV or use --discover."
        outfile.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"institute_code": code, "institute_name": name, "url": "", "url_source": "", "pages_crawled": 0, "pdfs_found": 0, "placement_mentions": 0, "historical_years": "", "errors": 0, "status": "needs_url"}

    if is_bad_domain(url):
        result["status"] = "bad_domain"
        result["message"] = "URL is not an allowed official-site domain."
        outfile.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"institute_code": code, "institute_name": name, "url": url, "url_source": url_source, "pages_crawled": 0, "pdfs_found": 0, "placement_mentions": 0, "historical_years": "", "errors": 1, "status": "bad_domain"}

    logging.info("[%s] %s -> %s", code, name, url)
    pdf_dir = args.out / "pdfs" / code if args.save_pdfs else None
    pages, documents, errors = crawl_site(url, session, args, pdf_dir)
    extracted, historical = extract_information(pages, documents, args.wanted_years)

    result["status"] = "ok"
    result["crawl"]["pages_crawled"] = list(pages.keys())
    result["crawl"]["pdf_count"] = len(documents)
    result["crawl"]["errors"] = errors
    result["extracted"] = extracted
    result["historical"] = historical
    result["raw_text_pages"] = pages
    result["raw_text_pdfs"] = {d["url"]: d.get("text", "") for d in documents if d.get("text_available")}
    result["documents"] = [{k: v for k, v in d.items() if k != "text"} for d in documents]
    result["quality"] = {
        "html_sources": len(pages),
        "pdf_text_sources": sum(1 for d in documents if d.get("text_available")),
        "placement_evidence": len(extracted["placement_mentions"]),
        "fee_evidence": len(extracted["fees"]),
        "historical_years_found": sorted(historical.keys()),
        "needs_manual_review": True,
    }
    outfile.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"institute_code": code, "institute_name": name, "url": url, "url_source": url_source, "pages_crawled": len(pages), "pdfs_found": len(documents), "placement_mentions": len(extracted["placement_mentions"]), "historical_years": " | ".join(sorted(historical.keys())), "errors": len(errors), "status": "ok"}


def write_csv(path, rows):
    columns = ["institute_code", "institute_name", "url", "url_source", "pages_crawled", "pdfs_found", "placement_mentions", "historical_years", "errors", "status"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="Fast evidence-first college website + PDF scraper")
    ap.add_argument("--colleges", required=True, help="path to college_master.csv")
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--college-code", default="", help="only one institute_code")
    ap.add_argument("--url", default="", help="known official URL for --college-code")
    ap.add_argument("--limit", type=int, default=0, help="first N colleges; 0=all")
    ap.add_argument("--resume", action="store_true", help="skip existing JSON outputs")
    ap.add_argument("--discover", action="store_true", help="bounded DDG/Bing URL discovery")
    ap.add_argument("--workers", type=int, default=6, help="parallel colleges")
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--max-pdfs", type=int, default=12)
    ap.add_argument("--max-pdf-pages", type=int, default=40)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--search-timeout", type=int, default=5)
    ap.add_argument("--years", default="2020,2021,2022,2023,2024,2025")
    ap.add_argument("--save-pdfs", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s | %(levelname)s | %(message)s")
    args.out = Path(args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    args.wanted_years = {x.strip() for x in args.years.split(",") if x.strip()}

    rows = select_rows(load_rows(args.colleges), args.college_code or None, args.limit)
    if not rows:
        raise SystemExit("No colleges selected.")
    if pymupdf is None:
        logging.warning("PyMuPDF not installed: PDF text will not be extracted.")

    metadata = {"version": VERSION, "started_at": now_iso(), "input": str(Path(args.colleges)), "output": str(args.out), "selected_colleges": len(rows), "workers": args.workers, "discover": args.discover, "max_pages": args.max_pages, "max_pdfs": args.max_pdfs, "years": sorted(args.wanted_years)}
    (args.out / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Starting: {len(rows)} college(s)")
    print(f"Output:   {args.out}/")
    print(f"Workers:  {args.workers}")

    summaries = []
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(scrape_one, row, args): row for row in rows}
        done = 0
        for future in as_completed(futures):
            row = futures[future]
            try:
                s = future.result()
            except Exception as exc:
                s = {"institute_code": row.get("institute_code", ""), "institute_name": row.get("institute_name", ""), "url": "", "url_source": "", "pages_crawled": 0, "pdfs_found": 0, "placement_mentions": 0, "historical_years": "", "errors": 1, "status": f"error:{str(exc)[:150]}"}
            with lock:
                summaries.append(s)
                done += 1
                print(f"[{done}/{len(rows)}] {s.get('institute_code')} {s.get('status')} pages={s.get('pages_crawled')} pdfs={s.get('pdfs_found')}")

    summaries.sort(key=lambda x: x.get("institute_code", ""))
    write_csv(args.out / "scrape_summary.csv", summaries)
    needs = [s for s in summaries if s.get("status") == "needs_url"]
    failed = [s for s in summaries if str(s.get("status", "")).startswith("error") or s.get("status") == "bad_domain"]
    write_csv(args.out / "needs_url.csv", needs)
    write_csv(args.out / "failed.csv", failed)

    metadata.update({"finished_at": now_iso(), "successful": sum(s.get("status") == "ok" for s in summaries), "skipped": sum(s.get("status") == "skipped" for s in summaries), "needs_url": len(needs), "failed": len(failed)})
    (args.out / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print("\n===================================")
    print("SCRAPER FINISHED")
    print("===================================")
    print(f"Processed : {len(summaries)}")
    print(f"Successful: {metadata['successful']}")
    print(f"Skipped   : {metadata['skipped']}")
    print(f"Needs URL : {metadata['needs_url']}")
    print(f"Failed    : {metadata['failed']}")
    print(f"Output    : {args.out}/")


if __name__ == "__main__":
    main()
