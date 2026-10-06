#!/usr/bin/env python3
"""
College information + placement evidence scraper (v2)

Purpose
-------
Build a stronger, provenance-first college information dataset from official
college websites and official PDFs linked from those sites.

Key features
------------
1. Reads college_master.csv produced by build_college_list.py.
2. Can process one college with --college-code.
3. Can force an official URL with --url (recommended for the first test).
4. If URL is missing, discovers candidates using DuckDuckGo HTML search.
5. Validates the chosen website before crawling.
6. Crawls same-domain HTML pages with a priority queue.
7. Finds relevant PDFs (placement reports, NIRF, mandatory disclosure, annual
   reports, accreditation, admissions/fees, etc.) and extracts PDF text when
   PyMuPDF (fitz) is installed.
8. Extracts evidence with source URL, source type, year(s), context and
   confidence. Regex is only a candidate extractor; evidence is preserved.
9. Builds a year-indexed placement view for years mentioned in source text.
10. Supports resume mode and configurable page/PDF limits and delay.
11. Writes a per-college JSON plus a run summary CSV.

Install
-------
    pip install requests beautifulsoup4 pymupdf

Basic run (one college)
-----------------------
    python3 college_info_scraper_v2.py \
      --colleges ./V4_daataa/college_master.csv \
      --college-code 01012 \
      --url https://www.gcoey.ac.in/ \
      --out ./V4_daataa/college_info

Test only 1 college, discovered URL
------------------------------------
    python3 college_info_scraper_v2.py \
      --colleges ./V4_daataa/college_master.csv \
      --college-code 01012 \
      --out ./V4_daataa/college_info

Later: all 703 colleges
-----------------------
    python3 college_info_scraper_v2.py \
      --colleges ./V4_daataa/college_master.csv \
      --out ./V4_daataa/college_info \
      --resume

Notes
-----
- This script does not invent missing historical placement data.
- "2020-2025" means it searches available official pages/PDFs for those
  years and records what it actually finds.
- Search-engine discovery is inherently fallible. Prefer --url for colleges
  where the official site is known.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


PARSER_VERSION = "1.0-evidence-pdf-v2"

USER_AGENT = (
    "AI-Con-CollegeEvidenceBot/1.0 "
    "(educational research; contact project-owner)"
)

SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/?q="

DEFAULT_MAX_PAGES = 30
DEFAULT_MAX_PDFS = 25
DEFAULT_DELAY = 1.5
DEFAULT_TIMEOUT = 20
DEFAULT_MAX_PDF_PAGES = 50
DEFAULT_MAX_TEXT_CHARS_PER_SOURCE = 250_000

BAD_DOMAINS = {
    "facebook.com",
    "wikipedia.org",
    "youtube.com",
    "instagram.com",
    "linkedin.com",
    "shiksha.com",
    "collegedunia.com",
    "careers360.com",
    "getmyuni.com",
    "collegedekho.com",
    "zollege.in",
    "targetadmission.com",
    "justdial.com",
}

PRIORITY_KEYWORDS = {
    "placement": 10,
    "placements": 10,
    "training and placement": 10,
    "tpo": 8,
    "career": 6,
    "nirf": 8,
    "mandatory disclosure": 10,
    "accreditation": 7,
    "naac": 7,
    "nba": 7,
    "annual report": 8,
    "placement report": 12,
    "recruiter": 8,
    "recruiters": 8,
    "package": 7,
    "highest package": 9,
    "average package": 9,
    "median salary": 9,
    "fee": 6,
    "fees": 6,
    "admission": 4,
    "hostel": 4,
    "infrastructure": 3,
    "facilities": 3,
    "contact": 2,
    "about": 2,
}

PDF_KEYWORDS = (
    "placement",
    "nirf",
    "mandatory",
    "disclosure",
    "annual",
    "report",
    "accredit",
    "naac",
    "nba",
    "fee",
    "fees",
    "admission",
    "brochure",
    "prospectus",
    "iqac",
    "audit",
    "recruit",
)


YEAR_RANGE_RE = re.compile(
    r"\b((?:19|20)\d{2})\s*[-/–]\s*((?:19|20)?\d{2})\b"
)
YEAR_RE = re.compile(r"\b(20(?:19|20|21|22|23|24|25|26))\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}|\d{3,5}[-\s]\d{6,8}")

NAAC_RE = re.compile(
    r"\bNAAC\b[^.\n]{0,120}?\b("
    r"A\+\+|A\+|A-|A|B\+\+|B\+|B-|B|C|D"
    r")\b",
    re.I,
)

ESTABLISHED_RE = re.compile(
    r"\b(?:established|founded|established in|founded in|since)\D{0,20}"
    r"((?:18|19|20)\d{2})\b",
    re.I,
)

AFFILIATION_RE = re.compile(
    r"\baffiliated\s+(?:to|with)\s+([A-Z][^.]{5,160})",
    re.I,
)

PLACEMENT_RATE_RE = re.compile(
    r"(?P<value>\d{1,3}(?:\.\d+)?)\s*%\s*"
    r"(?P<context>.{0,100}?(?:placed|placement|placements|students))",
    re.I,
)

PACKAGE_RE = re.compile(
    r"(?P<value>(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d+)?)\s*"
    r"(?P<unit>lakh|lakhs|lpa|lac|crore|crores)?",
    re.I,
)

PACKAGE_LABEL_RE = re.compile(
    r"\b("
    r"highest package|average package|avg package|median package|lowest package|"
    r"salary package|ctc|package"
    r")\b[^.\n]{0,120}",
    re.I,
)

MEDIAN_RE = re.compile(
    r"\bmedian\s+(?:salary|package|ctc)?\D{0,30}"
    r"((?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d+)?)",
    re.I,
)

FEE_RE = re.compile(
    r"\b(?:annual\s+)?(?:tuition\s+)?fees?\b[^.\n]{0,100}"
    r"((?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d+)?)",
    re.I,
)

NBA_RE = re.compile(
    r"\bNBA\b[^.\n]{0,180}", re.I
)

NIRF_RE = re.compile(
    r"\bNIRF\b[^.\n]{0,200}", re.I
)

RECRUITER_RE = re.compile(
    r"\b(?:recruiters?|recruitment partners?|hiring partners?)\b[^.\n]{0,250}",
    re.I,
)

ADDRESS_RE = re.compile(
    r"\b(?:address|located at|location)\b\s*[:\-]?\s*([^.\n]{15,250})",
    re.I,
)

CONTACT_URL_HINTS = (
    "contact",
    "reach-us",
    "contact-us",
    "directory",
)

SKIP_URL_HINTS = (
    "login",
    "logout",
    "signin",
    "signup",
    "register",
    "captcha",
    "javascript:",
    "mailto:",
    "tel:",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", (value or "college").lower())
    return value.strip("_")[:70] or "college"


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    url, _ = urldefrag(url)
    return url.rstrip("/")


def domain_of(url: str) -> str:
    netloc = urlparse(url).netloc.lower().split("@")[-1]
    return netloc.split(":")[0].removeprefix("www.")


def is_bad_domain(url: str) -> bool:
    d = domain_of(url)
    return any(d == bad or d.endswith("." + bad) for bad in BAD_DOMAINS)


def same_domain(url_a: str, url_b: str) -> bool:
    return domain_of(url_a) == domain_of(url_b)


def extract_context(text: str, start: int, end: int, pad: int = 180) -> str:
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    return re.sub(r"\s+", " ", text[lo:hi]).strip()


def detect_years(text: str, wanted_years: set[str]) -> list[str]:
    found: set[str] = set()

    for m in YEAR_RANGE_RE.finditer(text):
        start = int(m.group(1))
        end_raw = m.group(2)
        if len(end_raw) == 2:
            end = (start // 100) * 100 + int(end_raw)
        else:
            end = int(end_raw)
        label = f"{start}-{end % 100:02d}"
        if not wanted_years or any(
            y in label or y[:4] == str(start) or y[:4] == str(end)
            for y in wanted_years
        ):
            found.add(label)

    for m in YEAR_RE.finditer(text):
        y = m.group(1)
        if not wanted_years or any(y in wanted for wanted in wanted_years):
            found.add(y)

    return sorted(found)


def candidate_score(url: str, anchor_text: str, college_name: str) -> int:
    lower = (url + " " + anchor_text).lower()
    score = 0

    if ".ac.in" in lower:
        score += 20
    if ".edu" in lower:
        score += 10
    if any(part in lower for part in slug(college_name).split("_") if len(part) >= 5):
        score += 1

    for keyword, weight in PRIORITY_KEYWORDS.items():
        if keyword in lower:
            score += weight

    if is_bad_domain(url):
        score -= 50

    return score


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"})
    return session


def ddg_search(query: str, session: requests.Session, timeout: int) -> list[str]:
    import urllib.parse

    url = SEARCH_ENDPOINT + urllib.parse.quote(query)
    try:
        r = session.get(url, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as exc:
        logging.warning("Search failed: %s", exc)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    found = []

    for a in soup.select("a.result__a, a.result__url"):
        href = a.get("href", "")
        if not href:
            continue

        # DuckDuckGo may return a redirect URL with ?uddg=<real_url>.
        parsed = urlparse(href)
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg:
            href = unquote(uddg[0])

        if href.startswith(("http://", "https://")):
            href = normalize_url(href)
            if not is_bad_domain(href):
                found.append(href)

    # preserve order + uniqueness
    return list(dict.fromkeys(found))


def discover_official_site(college_name: str, session: requests.Session, timeout: int) -> tuple[str | None, list[dict]]:
    queries = [
        f'"{college_name}" official website',
        f'"{college_name}" site:ac.in',
        f'"{college_name}" Maharashtra official',
    ]

    candidates: dict[str, dict] = {}

    for query in queries:
        for url in ddg_search(query, session, timeout):
            score = candidate_score(url, "", college_name)
            if url not in candidates or score > candidates[url]["score"]:
                candidates[url] = {
                    "url": url,
                    "score": score,
                    "query": query,
                }
        time.sleep(1.0)

    ranked = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)

    for candidate in ranked[:10]:
        url = candidate["url"]
        try:
            r = session.get(url, timeout=timeout, allow_redirects=True)
            content_type = r.headers.get("content-type", "").lower()
            if r.ok and "html" in content_type:
                final_url = normalize_url(r.url)
                if not is_bad_domain(final_url):
                    candidate["validated_url"] = final_url
                    candidate["status"] = r.status_code
                    return final_url, ranked
        except requests.RequestException as exc:
            candidate["validation_error"] = str(exc)[:200]

    return None, ranked


def get_robots(url: str, session: requests.Session, timeout: int):
    # Kept intentionally simple: if robots.txt can't be fetched, don't block
    # the run; still use a conservative crawler with same-domain + delay.
    from urllib.robotparser import RobotFileParser

    rp = RobotFileParser()
    base = urlparse(url)
    robots_url = f"{base.scheme}://{base.netloc}/robots.txt"

    try:
        r = session.get(robots_url, timeout=timeout)
        if r.ok and r.text:
            rp.parse(r.text.splitlines())
            return rp
    except requests.RequestException:
        pass

    return None


def link_priority(url: str, anchor_text: str) -> int:
    lower = (url + " " + anchor_text).lower()
    score = 0
    for keyword, weight in PRIORITY_KEYWORDS.items():
        if keyword in lower:
            score += weight
    for hint in CONTACT_URL_HINTS:
        if hint in lower:
            score += 3
    return score


def looks_like_pdf(url: str, anchor_text: str = "") -> bool:
    lower = (url + " " + anchor_text).lower()
    return lower.endswith(".pdf") or ".pdf?" in lower


def clean_html_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:DEFAULT_MAX_TEXT_CHARS_PER_SOURCE]


def crawl_site(
    root_url: str,
    session: requests.Session,
    max_pages: int,
    max_pdfs: int,
    delay: float,
    timeout: int,
    max_pdf_pages: int,
    wanted_years: set[str],
    save_pdf_dir: Path | None,
) -> tuple[dict[str, str], list[dict], list[dict], list[str]]:
    """
    Returns:
      pages: {url: extracted_text}
      pdfs: [{url,title,source_page,pages,text,error,...}]
      errors: list
      visited_order: list
    """
    robots = get_robots(root_url, session, timeout)

    root = normalize_url(root_url)
    heap = [(-100, 0, root)]
    queued = {root}
    pages: dict[str, str] = {}
    pdfs: list[dict] = []
    errors: list[dict] = []
    visited_order: list[str] = []

    seq = 1
    last_request = 0.0

    while heap and len(pages) < max_pages:
        _, _, url = heapq.heappop(heap)
        if url in pages:
            continue

        if robots is not None and not robots.can_fetch(USER_AGENT, url):
            errors.append({"url": url, "error": "blocked_by_robots_txt"})
            continue

        wait = delay - (time.time() - last_request)
        if wait > 0:
            time.sleep(wait)

        try:
            r = session.get(url, timeout=timeout, allow_redirects=True)
            last_request = time.time()
        except requests.RequestException as exc:
            last_request = time.time()
            errors.append({"url": url, "error": str(exc)[:300]})
            continue

        if r.status_code >= 400:
            errors.append({"url": url, "error": f"http_{r.status_code}"})
            continue

        final_url = normalize_url(r.url)
        content_type = r.headers.get("content-type", "").lower()

        if "application/pdf" in content_type or looks_like_pdf(final_url):
            if len(pdfs) >= max_pdfs:
                continue

            pdf_item = {
                "url": final_url,
                "source_page": None,
                "title": Path(urlparse(final_url).path).name,
                "pages": 0,
                "text": "",
                "text_available": False,
                "error": None,
            }

            try:
                data = r.content
                if save_pdf_dir is not None:
                    save_pdf_dir.mkdir(parents=True, exist_ok=True)
                    filename = slug(Path(urlparse(final_url).path).stem)[:90] + ".pdf"
                    target = save_pdf_dir / filename
                    # Avoid overwriting different files with same slug.
                    idx = 2
                    while target.exists():
                        target = save_pdf_dir / f"{slug(Path(urlparse(final_url).path).stem)[:80]}_{idx}.pdf"
                        idx += 1
                    target.write_bytes(data)
                    pdf_item["local_file"] = str(target)

                if fitz is None:
                    pdf_item["error"] = "PyMuPDF not installed; PDF text not extracted"
                else:
                    doc = fitz.open(stream=data, filetype="pdf")
                    chunks = []
                    pages_to_read = min(len(doc), max_pdf_pages)
                    for pno in range(pages_to_read):
                        chunks.append(doc.load_page(pno).get_text("text"))
                    pdf_item["pages"] = len(doc)
                    pdf_item["text"] = re.sub(
                        r"\s+", " ", "\n".join(chunks)
                    )[:DEFAULT_MAX_TEXT_CHARS_PER_SOURCE]
                    pdf_item["text_available"] = bool(pdf_item["text"])
                    doc.close()
            except Exception as exc:
                pdf_item["error"] = str(exc)[:300]

            pdfs.append(pdf_item)
            continue

        if "html" not in content_type:
            continue

        soup = BeautifulSoup(r.content, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        text = clean_html_text(soup)
        pages[final_url] = text
        visited_order.append(final_url)

        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href or href.lower().startswith(SKIP_URL_HINTS):
                continue

            link = normalize_url(urljoin(final_url, href))
            if not link or is_bad_domain(link):
                continue

            anchor_text = a.get_text(" ", strip=True)
            if looks_like_pdf(link, anchor_text):
                if len(pdfs) < max_pdfs and link not in queued:
                    heapq.heappush(heap, (-1000, seq, link))
                    queued.add(link)
                    seq += 1
                continue

            if not same_domain(root, link):
                continue
            if link in queued or link in pages:
                continue

            # Avoid obvious query-heavy or executable endpoints.
            parsed = urlparse(link)
            if len(parsed.query) > 120:
                continue

            priority = link_priority(link, anchor_text)
            heapq.heappush(heap, (-priority, seq, link))
            queued.add(link)
            seq += 1

    return pages, pdfs, errors, visited_order


def evidence_item(
    value,
    kind: str,
    context: str,
    source_url: str,
    source_type: str,
    years: list[str],
    confidence: str = "heuristic",
) -> dict:
    return {
        "value": value,
        "kind": kind,
        "years_mentioned": years,
        "context": context,
        "source_url": source_url,
        "source_type": source_type,
        "confidence": confidence,
    }


def extract_from_sources(
    pages: dict[str, str],
    pdfs: list[dict],
    wanted_years: set[str],
) -> tuple[dict, dict[str, dict]]:
    sources: list[tuple[str, str, str]] = []

    for url, text in pages.items():
        sources.append((url, "html", text))

    for item in pdfs:
        if item.get("text_available"):
            sources.append((item["url"], "pdf", item.get("text", "")))

    fields = {
        "naac": [],
        "nba": [],
        "nirf": [],
        "established_year": [],
        "affiliation": [],
        "address": [],
        "fees": [],
        "placement_mentions": [],
        "recruiter_mentions": [],
        "contact": {"emails": set(), "phones": set()},
    }

    historical: dict[str, dict] = defaultdict(
        lambda: {
            "placement": [],
            "packages": [],
            "fees": [],
            "other": [],
            "sources": set(),
        }
    )

    seen_keys = set()

    for source_url, source_type, text in sources:
        # Basic contact extraction
        fields["contact"]["emails"].update(EMAIL_RE.findall(text))
        fields["contact"]["phones"].update(PHONE_RE.findall(text))

        def add_evidence(bucket: str, item: dict):
            key = (
                bucket,
                str(item.get("value")),
                item.get("source_url"),
                item.get("context", "")[:100],
            )
            if key not in seen_keys:
                seen_keys.add(key)
                fields[bucket].append(item)

        for m in NAAC_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            add_evidence(
                "naac",
                evidence_item(m.group(1), "naac_grade", ctx, source_url, source_type,
                              detect_years(ctx, wanted_years)),
            )

        for m in NBA_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            add_evidence(
                "nba",
                evidence_item(m.group(0).strip(), "nba", ctx, source_url, source_type,
                              detect_years(ctx, wanted_years)),
            )

        for m in NIRF_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            add_evidence(
                "nirf",
                evidence_item(m.group(0).strip(), "nirf", ctx, source_url, source_type,
                              detect_years(ctx, wanted_years)),
            )

        for m in ESTABLISHED_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            add_evidence(
                "established_year",
                evidence_item(m.group(1), "established_year", ctx, source_url, source_type,
                              detect_years(ctx, wanted_years)),
            )

        for m in AFFILIATION_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            add_evidence(
                "affiliation",
                evidence_item(m.group(1).strip(), "affiliation", ctx, source_url, source_type,
                              detect_years(ctx, wanted_years)),
            )

        for m in ADDRESS_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            add_evidence(
                "address",
                evidence_item(m.group(1).strip(), "address", ctx, source_url, source_type,
                              detect_years(ctx, wanted_years)),
            )

        for m in FEE_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            years = detect_years(ctx, wanted_years)
            item = evidence_item(m.group(1), "fee_rupees", ctx, source_url, source_type, years)
            add_evidence("fees", item)
            for y in years:
                historical[y]["fees"].append(item)
                historical[y]["sources"].add(source_url)

        for m in PACKAGE_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            if not any(
                key in ctx.lower()
                for key in ("placement", "package", "ctc", "salary", "lpa", "recruit")
            ):
                continue

            value = m.group(0).strip()
            years = detect_years(ctx, wanted_years)
            item = evidence_item(
                value,
                "package_rupees",
                ctx,
                source_url,
                source_type,
                years,
            )
            add_evidence("placement_mentions", item)
            for y in years:
                historical[y]["packages"].append(item)
                historical[y]["sources"].add(source_url)

        for m in MEDIAN_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            years = detect_years(ctx, wanted_years)
            item = evidence_item(
                m.group(1),
                "median_salary_or_package",
                ctx,
                source_url,
                source_type,
                years,
            )
            add_evidence("placement_mentions", item)
            for y in years:
                historical[y]["packages"].append(item)
                historical[y]["sources"].add(source_url)

        for m in PLACEMENT_RATE_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            years = detect_years(ctx, wanted_years)
            item = evidence_item(
                m.group("value") + "%",
                "placement_rate",
                ctx,
                source_url,
                source_type,
                years,
            )
            add_evidence("placement_mentions", item)
            for y in years:
                historical[y]["placement"].append(item)
                historical[y]["sources"].add(source_url)

        for m in PACKAGE_LABEL_RE.finditer(text):
            ctx = extract_context(text, *m.span())
            years = detect_years(ctx, wanted_years)
            item = evidence_item(
                m.group(1),
                "package_label",
                ctx,
                source_url,
                source_type,
                years,
            )
            add_evidence("placement_mentions", item)
            for y in years:
                historical[y]["other"].append(item)
                historical[y]["sources"].add(source_url)

        for m in RECRUITER_RE.finditer(text):
            ctx = extract_context(text, *m.span(), pad=220)
            add_evidence(
                "recruiter_mentions",
                evidence_item(
                    m.group(0).strip(),
                    "recruiter_mention",
                    ctx,
                    source_url,
                    source_type,
                    detect_years(ctx, wanted_years),
                ),
            )

    # De-duplicate and turn sets into JSON-friendly structures.
    fields["contact"]["emails"] = sorted(fields["contact"]["emails"])[:20]
    fields["contact"]["phones"] = sorted(fields["contact"]["phones"])[:20]

    historical_out = {}
    for year, data in sorted(historical.items()):
        historical_out[year] = {
            "placement": data["placement"][:50],
            "packages": data["packages"][:50],
            "fees": data["fees"][:30],
            "other": data["other"][:30],
            "sources": sorted(data["sources"]),
        }

    return fields, historical_out


def load_colleges(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def select_rows(rows: list[dict], college_code: str | None, limit: int) -> list[dict]:
    if college_code:
        selected = [r for r in rows if r.get("institute_code") == college_code]
        if not selected:
            raise SystemExit(f"No college with institute_code={college_code!r} found in CSV.")
        return selected[:1]

    if limit:
        return rows[:limit]

    return rows


def write_summary(out_dir: Path, summaries: list[dict]) -> None:
    path = out_dir / "scrape_summary.csv"
    cols = [
        "institute_code",
        "institute_name",
        "url",
        "url_source",
        "pages_crawled",
        "pdfs_found",
        "errors",
        "placement_mentions",
        "historical_years_found",
        "status",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in summaries:
            writer.writerow({c: row.get(c, "") for c in cols})


def scrape_one(
    row: dict,
    session: requests.Session,
    out_dir: Path,
    args,
) -> dict:
    code = (row.get("institute_code") or "").strip()
    name = (row.get("institute_name") or "").strip()

    out_file = out_dir / f"{code}_{slug(name)}.json"

    if args.resume and out_file.exists():
        logging.info("Skipping existing: %s", out_file)
        return {
            "institute_code": code,
            "institute_name": name,
            "url": "",
            "url_source": "resume_skip",
            "pages_crawled": "",
            "pdfs_found": "",
            "errors": "",
            "placement_mentions": "",
            "historical_years_found": "",
            "status": "skipped",
        }

    started = time.time()

    forced_url = normalize_url(args.url) if args.url else ""
    row_url = normalize_url(row.get("url") or "")

    if forced_url:
        url = forced_url
        url_source = "provided_cli"
    elif row_url:
        url = row_url
        url_source = "provided_csv"
    else:
        url, candidates = discover_official_site(name, session, args.timeout)
        url_source = "auto_search" if url else None

    result = {
        "schema_version": PARSER_VERSION,
        "institute_code": code,
        "institute_name": name,
        "url": url,
        "url_source": url_source,
        "scraped_at": now_iso(),
        "requested_history_years": sorted(args.wanted_years),
        "crawl": {
            "max_pages": args.max_pages,
            "max_pdfs": args.max_pdfs,
            "delay_seconds": args.delay,
            "pages_crawled": [],
            "pdfs_found": 0,
            "errors": [],
            "duration_seconds": None,
        },
        "extracted": None,
        "historical": {},
        "documents": [],
    }

    if not url:
        result["error"] = "no official site found"
        result["search_note"] = "Prefer supplying --url for this college."
        out_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return {
            **{k: result.get(k) for k in ["institute_code", "institute_name", "url", "url_source"]},
            "pages_crawled": 0,
            "pdfs_found": 0,
            "errors": 1,
            "placement_mentions": 0,
            "historical_years_found": "",
            "status": "no_url",
        }

    if is_bad_domain(url):
        result["error"] = "blocked_or_non_official_domain"
        out_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return {
            "institute_code": code,
            "institute_name": name,
            "url": url,
            "url_source": url_source,
            "pages_crawled": 0,
            "pdfs_found": 0,
            "errors": 1,
            "placement_mentions": 0,
            "historical_years_found": "",
            "status": "bad_domain",
        }

    logging.info("Scraping %s | %s", code, name)
    logging.info("URL: %s (%s)", url, url_source)

    pdf_dir = None
    if args.save_pdfs:
        pdf_dir = out_dir / "pdfs" / code

    pages, pdfs, errors, visited = crawl_site(
        root_url=url,
        session=session,
        max_pages=args.max_pages,
        max_pdfs=args.max_pdfs,
        delay=args.delay,
        timeout=args.timeout,
        max_pdf_pages=args.max_pdf_pages,
        wanted_years=args.wanted_years,
        save_pdf_dir=pdf_dir,
    )

    fields, historical = extract_from_sources(
        pages=pages,
        pdfs=pdfs,
        wanted_years=args.wanted_years,
    )

    result["crawl"]["pages_crawled"] = visited
    result["crawl"]["pdfs_found"] = len(pdfs)
    result["crawl"]["errors"] = errors
    result["crawl"]["duration_seconds"] = round(time.time() - started, 2)

    result["extracted"] = fields
    result["extracted"]["contact"]["emails"] = fields["contact"]["emails"]
    result["extracted"]["contact"]["phones"] = fields["contact"]["phones"]
    result["historical"] = historical

    for item in pdfs:
        doc_meta = dict(item)
        doc_meta.pop("text", None)
        result["documents"].append(doc_meta)

    # Add simple quality flags.
    result["quality"] = {
        "has_official_url": bool(url),
        "has_html_content": bool(pages),
        "has_pdf_content": any(p.get("text_available") for p in pdfs),
        "placement_evidence_count": len(fields["placement_mentions"]),
        "historical_years_found": sorted(historical.keys()),
        "warning": (
            "Extracted figures are evidence candidates from source text. "
            "Review source_url/context before using them in a user-facing answer."
        ),
    }

    out_file.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "institute_code": code,
        "institute_name": name,
        "url": url,
        "url_source": url_source,
        "pages_crawled": len(pages),
        "pdfs_found": len(pdfs),
        "errors": len(errors),
        "placement_mentions": len(fields["placement_mentions"]),
        "historical_years_found": " | ".join(sorted(historical.keys())),
        "status": "ok",
    }


def build_parser():
    ap = argparse.ArgumentParser(
        description="Evidence-first college website + PDF scraper."
    )
    ap.add_argument(
        "--colleges",
        required=True,
        help="college_master.csv from build_college_list.py",
    )
    ap.add_argument(
        "--out",
        required=True,
        help="Output directory",
    )
    ap.add_argument(
        "--college-code",
        default="",
        help="Process only one institute_code",
    )
    ap.add_argument(
        "--url",
        default="",
        help="Force a known official URL for the selected college",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process first N colleges (0 = all)",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Skip colleges whose JSON already exists",
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Maximum HTML pages per college (default {DEFAULT_MAX_PAGES})",
    )
    ap.add_argument(
        "--max-pdfs",
        type=int,
        default=DEFAULT_MAX_PDFS,
        help=f"Maximum PDFs per college (default {DEFAULT_MAX_PDFS})",
    )
    ap.add_argument(
        "--max-pdf-pages",
        type=int,
        default=DEFAULT_MAX_PDF_PAGES,
        help=f"Maximum pages read from each PDF (default {DEFAULT_MAX_PDF_PAGES})",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Delay between requests to the same site (default {DEFAULT_DELAY})",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout seconds (default {DEFAULT_TIMEOUT})",
    )
    ap.add_argument(
        "--years",
        default="2020,2021,2022,2023,2024,2025",
        help="Comma-separated years to look for in evidence",
    )
    ap.add_argument(
        "--save-pdfs",
        action="store_true",
        help="Save discovered PDFs locally under <out>/pdfs/<college_code>/",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose logging",
    )
    return ap


def main():
    args = build_parser().parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    args.wanted_years = {
        token.strip()
        for token in args.years.split(",")
        if token.strip()
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    colleges_path = Path(args.colleges)
    if not colleges_path.exists():
        raise SystemExit(f"College CSV not found: {colleges_path}")

    rows = load_colleges(colleges_path)
    rows = select_rows(rows, args.college_code or None, args.limit)

    if not rows:
        raise SystemExit("No colleges selected.")

    session = make_session()
    summaries = []

    for i, row in enumerate(rows, start=1):
        code = row.get("institute_code", "")
        name = row.get("institute_name", "")
        print(f"[{i}/{len(rows)}] {code} {name}")

        try:
            summary = scrape_one(row, session, out_dir, args)
        except Exception as exc:
            logging.exception("Unhandled error for %s", code)
            summary = {
                "institute_code": code,
                "institute_name": name,
                "url": "",
                "url_source": "",
                "pages_crawled": 0,
                "pdfs_found": 0,
                "errors": 1,
                "placement_mentions": 0,
                "historical_years_found": "",
                "status": f"error:{exc}",
            }

        summaries.append(summary)

    write_summary(out_dir, summaries)

    ok = sum(1 for s in summaries if s.get("status") == "ok")
    print()
    print(f"Done. Output: {out_dir}/")
    print(f"Processed: {len(summaries)} | Successful: {ok}")
    print(f"Summary: {out_dir / 'scrape_summary.csv'}")
    print(
        "Reminder: historical years are only reported when evidence containing "
        "those years was actually found on the crawled official pages/PDFs."
    )


if __name__ == "__main__":
    main()
