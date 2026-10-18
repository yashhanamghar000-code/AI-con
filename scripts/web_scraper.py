#!/usr/bin/env python3
"""
AI-CON Web Scraper
==================
Fetches college information from the web when local data is missing.
Searches across multiple authoritative sources and returns structured data.

Sources searched (in priority order):
  1. Shiksha.com        - placements, fees, reviews
  2. CollegeDekho.com   - affiliation, NAAC, contacts
  3. DuckDuckGo         - fallback for any fact

Data returned is cleaned and structured to match the AI-CON schema.
"""
from __future__ import annotations

import re
import time
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# HTTP helpers  (requests with retry + timeout)
# ─────────────────────────────────────────────

def _make_session():
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        s = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5,
                      status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://",  HTTPAdapter(max_retries=retry))
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-IN,en;q=0.9",
        })
        return s
    except ImportError:
        return None


def _fetch(url: str, session=None, timeout: int = 10) -> Optional[str]:
    """Fetch a URL and return raw HTML text, or None on failure."""
    try:
        if session is None:
            import requests
            r = requests.get(url, timeout=timeout)
        else:
            r = session.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.text
        logger.debug("HTTP %s for %s", r.status_code, url)
    except Exception as exc:
        logger.debug("Fetch failed %s: %s", url, exc)
    return None


def _text_only(html: str) -> str:
    """Strip HTML tags; collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─────────────────────────────────────────────
# Extraction helpers
# ─────────────────────────────────────────────

def _extract_fees(text: str) -> Optional[str]:
    patterns = [
        r"(?:annual|total|tuition)\s+fee[s]?\s*[:\-]?\s*([\u20B9Rs\.]+\s*[\d,]+(?:\s*(?:lakh|lakhs|L|K)?)?)",
        r"fee[s]?\s*[:\-]\s*([\u20B9Rs\.]+\s*[\d,]+(?:\s*(?:lakh|lakhs|L|K)?)?)",
        r"([\u20B9Rs\.]+\s*[\d,]{3,}(?:\s*(?:lakh|lakhs|L|K))?)\s*(?:per year|p\.a\.|annually)",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(1).strip()
    return None


def _extract_package(text: str) -> Optional[str]:
    patterns = [
        r"(?:average|avg|median)\s+(?:package|salary|CTC)\s*[:\-]?\s*([\u20B9Rs\.]+\s*[\d\.]+\s*(?:LPA|lpa|L|Lakhs|lakhs)?)",
        r"(?:package|salary|CTC)\s*[:\-]\s*([\u20B9Rs\.]+\s*[\d\.]+\s*(?:LPA|lpa|L|Lakhs|lakhs)?)",
        r"([\d\.]+\s*(?:LPA|lpa)\s*(?:average|avg|median|package|salary)?)",
        r"highest\s+(?:package|salary)\s*[:\-]?\s*([\u20B9Rs\.]+\s*[\d\.]+\s*(?:LPA|lpa|L|Lakhs|lakhs)?)",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(1).strip()
    return None


def _extract_naac(text: str) -> Optional[str]:
    m = re.search(r"NAAC\s*(?:grade|accredited|rating)?\s*[:\-]?\s*([A-C]\+?\+?)", text, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"([A-C]\+?\+?)\s*(?:grade)?\s*(?:by)?\s*NAAC", text, re.I)
    if m:
        return m.group(1).upper()
    return None


def _extract_nirf(text: str) -> Optional[str]:
    m = re.search(r"NIRF\s*(?:rank(?:ing)?|rated)?\s*[:\-]?\s*(\d+)", text, re.I)
    if m:
        return m.group(1)
    return None


def _extract_affiliation(text: str) -> Optional[str]:
    patterns = [
        r"affiliated\s+(?:to|with)\s+([A-Za-z][^.]{5,80}?(?:University|Institute|Board))",
        r"affiliation\s*[:\-]\s*([A-Za-z][^.]{5,80}?(?:University|Institute|Board))",
        r"under\s+([A-Za-z][^.]{5,60}?(?:University|Institute|Board))",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            aff = m.group(1).strip()
            if len(aff) > 5:
                return aff
    return None


def _extract_established(text: str) -> Optional[str]:
    m = re.search(r"(?:established|founded|inception)\s*(?:in)?\s*[:\-]?\s*((?:19|20)\d{2})", text, re.I)
    if m:
        return m.group(1)
    return None


# ─────────────────────────────────────────────
# Per-source scrapers
# ─────────────────────────────────────────────

def _scrape_shiksha(college_name: str, session) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    query = quote_plus(f"{college_name} engineering Maharashtra")
    url = f"https://www.shiksha.com/search?q={query}&type=college"
    html = _fetch(url, session, timeout=12)
    if not html:
        return data
    text = _text_only(html)

    fee = _extract_fees(text)
    if fee:
        data["annual_fee_scraped"] = fee

    pkg = _extract_package(text)
    if pkg:
        data["avg_package_scraped"] = pkg

    naac = _extract_naac(text)
    if naac:
        data["naac_grade_scraped"] = naac

    m = re.search(r"placement[s]?[^.]{0,20}((?:[^.]+\.){1,4})", text, re.I)
    if m:
        data["placement_snippet_scraped"] = m.group(0)[:500].strip()

    data["_source"] = "shiksha.com"
    return data


def _scrape_collegedekho(college_name: str, session) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    query = quote_plus(f"{college_name} Maharashtra engineering college")
    url = f"https://www.collegedekho.com/search/?q={query}"
    html = _fetch(url, session, timeout=12)
    if not html:
        return data
    text = _text_only(html)

    aff = _extract_affiliation(text)
    if aff:
        data["affiliation_scraped"] = aff

    naac = _extract_naac(text)
    if naac:
        data["naac_grade_scraped"] = naac

    est = _extract_established(text)
    if est:
        data["established_scraped"] = est

    nirf = _extract_nirf(text)
    if nirf:
        data["nirf_rank_scraped"] = nirf

    data["_source"] = "collegedekho.com"
    return data


def _scrape_duckduckgo(college_name: str, session) -> Dict[str, Any]:
    """Fallback: DuckDuckGo HTML search (doesn't block scraping)."""
    data: Dict[str, Any] = {}
    query = quote_plus(f"{college_name} Maharashtra engineering NAAC fee placement affiliation")
    url = f"https://html.duckduckgo.com/html/?q={query}"
    html = _fetch(url, session, timeout=14)
    if not html:
        return data
    text = _text_only(html)[:8000]

    aff = _extract_affiliation(text)
    if aff:
        data["affiliation_scraped"] = aff

    fee = _extract_fees(text)
    if fee:
        data["annual_fee_scraped"] = fee

    pkg = _extract_package(text)
    if pkg:
        data["avg_package_scraped"] = pkg

    naac = _extract_naac(text)
    if naac:
        data["naac_grade_scraped"] = naac

    est = _extract_established(text)
    if est:
        data["established_scraped"] = est

    nirf = _extract_nirf(text)
    if nirf:
        data["nirf_rank_scraped"] = nirf

    m = re.search(r"placement[s]?[^.]{0,20}((?:[^.]+\.){1,4})", text, re.I)
    if m:
        data["placement_snippet_scraped"] = m.group(0)[:500].strip()

    data["_source"] = "duckduckgo.com (fallback)"
    return data


# ─────────────────────────────────────────────
# Public interface
# ─────────────────────────────────────────────

class CollegeWebScraper:
    """
    Multi-source web scraper for college info.

    Usage:
        scraper = CollegeWebScraper()
        result  = scraper.fetch("COEP Pune", institute_code="1002")
    """

    def __init__(self, delay_secs: float = 1.0):
        self._session = _make_session()
        self._delay = delay_secs

    def fetch(self, college_name: str, institute_code: Optional[str] = None) -> Dict[str, Any]:
        """Scrape college info from multiple web sources. Returns merged dict."""
        if not college_name or not college_name.strip():
            return {"error": "No college name provided"}

        name = college_name.strip()
        merged: Dict[str, Any] = {
            "college_name": name,
            "institute_code": institute_code or "",
            "_sources": [],
        }

        scrapers = [
            ("shiksha.com",     lambda: _scrape_shiksha(name, self._session)),
            ("collegedekho.com", lambda: _scrape_collegedekho(name, self._session)),
            ("duckduckgo.com",  lambda: _scrape_duckduckgo(name, self._session)),
        ]

        for src_name, fn in scrapers:
            try:
                result = fn()
                if result:
                    src = result.pop("_source", src_name)
                    merged["_sources"].append(src)
                    for k, v in result.items():
                        if v and k not in merged:   # never overwrite already-found data
                            merged[k] = v
            except Exception as exc:
                logger.warning("Scraper %s failed for '%s': %s", src_name, name, exc)
            time.sleep(self._delay)

        # Build a plain-text summary for vector embedding
        lines = [f"College: {name}"]
        if institute_code:
            lines.append(f"Institute Code: {institute_code}")
        for field in [
            "affiliation_scraped", "naac_grade_scraped", "nirf_rank_scraped",
            "established_scraped", "annual_fee_scraped", "avg_package_scraped",
            "placement_snippet_scraped",
        ]:
            val = merged.get(field)
            if val:
                label = field.replace("_scraped", "").replace("_", " ").title()
                lines.append(f"{label}: {val}")
        sources_str = ", ".join(merged.get("_sources", []))
        lines.append(f"Sources: {sources_str}")
        merged["raw_text_summary"] = "\n".join(lines)

        return merged

    def build_chroma_document(self, scraped: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert scraped data into ChromaDB-compatible format.

        Returns dict with keys: document (str), metadata (dict), id (str)
        """
        name   = scraped.get("college_name", "unknown")
        code   = scraped.get("institute_code", "")
        doc_id = "WEB_" + re.sub(r"[^A-Za-z0-9]", "_", name)[:40] + "_" + (code or "nocode")

        meta: Dict[str, Any] = {
            "institute_name":  name,
            "institute_code":  code,
            "chunk_type":      "web_scraped",
            "source_page":     ", ".join(scraped.get("_sources", ["web"])),
            "record_id":       doc_id,
        }
        for field in [
            "naac_grade_scraped", "nirf_rank_scraped", "established_scraped",
            "affiliation_scraped", "annual_fee_scraped", "avg_package_scraped",
        ]:
            val = scraped.get(field)
            if val:
                meta[field] = str(val)

        return {
            "document": scraped.get("raw_text_summary", name),
            "metadata": meta,
            "id": doc_id,
        }
