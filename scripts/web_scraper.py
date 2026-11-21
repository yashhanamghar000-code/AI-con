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

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Task 15: Sourced Scraped Field Model & Cache
# ─────────────────────────────────────────────

@dataclass
class ScrapedField:
    field_name: str
    value: Any
    source_url: str
    publisher: str
    retrieval_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    academic_or_placement_year: str = "2024-25"
    extraction_method: str = "regex_v1"
    verification_status: str = "secondary_unverified"  # "primary_verified", "secondary_unverified", "disputed"
    field_scope: str = "college_level"  # "college_level" | "branch_level"
    is_primary_source: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ScraperCache:
    """In-memory and file-backed cache with explicit TTL expiry for scraped facts."""

    def __init__(self, ttl_seconds: int = 86400 * 7):  # Default 7 days TTL
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._cache.get(key)
        if not entry:
            return None
        cached_time = entry.get("_timestamp", 0)
        if time.time() - cached_time > self.ttl_seconds:
            del self._cache[key]
            return None
        return entry.get("data")

    def set(self, key: str, data: Dict[str, Any]) -> None:
        self._cache[key] = {
            "data": data,
            "_timestamp": time.time(),
        }

    def clear(self) -> None:
        self._cache.clear()


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

def parse_fee_amount(fee_str: Optional[str]) -> Optional[float]:
    """Parse text fee string into a numerical float amount in INR."""
    if not fee_str:
        return None
    cleaned = fee_str.lower().replace("₹", "").replace("rs.", "").replace("rs", "").strip()
    m_lakh = re.search(r"([\d\.]+)\s*(?:lakh|lakhs|l)\b", cleaned)
    if m_lakh:
        try:
            return round(float(m_lakh.group(1)) * 100000.0, 2)
        except ValueError:
            pass
    m_k = re.search(r"([\d\.]+)\s*k\b", cleaned)
    if m_k:
        try:
            return round(float(m_k.group(1)) * 1000.0, 2)
        except ValueError:
            pass
    m_num = re.search(r"[\d,]+", cleaned)
    if m_num:
        try:
            val = float(m_num.group(0).replace(",", ""))
            if val > 1000:
                return round(val, 2)
        except ValueError:
            pass
    return None


def parse_package_amount(pkg_str: Optional[str]) -> Optional[float]:
    """Parse text placement salary package into a numerical float amount in INR."""
    if not pkg_str:
        return None
    cleaned = pkg_str.lower().replace("₹", "").replace("rs.", "").replace("rs", "").strip()
    m_lpa = re.search(r"([\d\.]+)\s*(?:lpa|lakh|lakhs|l)\b", cleaned)
    if m_lpa:
        try:
            return round(float(m_lpa.group(1)) * 100000.0, 2)
        except ValueError:
            pass
    m_num = re.search(r"[\d,]+", cleaned)
    if m_num:
        try:
            val = float(m_num.group(0).replace(",", ""))
            if val > 100000:
                return round(val, 2)
        except ValueError:
            pass
    return None


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

    def __init__(self, delay_secs: float = 1.0, cache_ttl_seconds: int = 86400 * 7):
        self._session = _make_session()
        self._delay = delay_secs
        self.cache = ScraperCache(ttl_seconds=cache_ttl_seconds)

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

    def enrich_missing_fields_safely(
        self,
        college_record: Dict[str, Any],
        target_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Task 15: Fallback enrichment strictly for missing non-cutoff fields without overwriting authoritative cutoffs."""
        PROTECTED_AUTHORITATIVE_FIELDS = {
            "institute_code", "institute_name", "cutoff_percentile", "closing_rank",
            "historical_cutoffs", "matching_branches", "predicted_cutoff", "predicted_rank"
        }

        enriched = dict(college_record)
        scraped_fields_provenance = enriched.setdefault("scraped_provenance", {})

        fields_to_check = target_fields or ["naac_grade", "nirf_rank", "established_year", "affiliation"]
        missing_fields = [f for f in fields_to_check if not enriched.get(f) and f not in PROTECTED_AUTHORITATIVE_FIELDS]

        if not missing_fields:
            return enriched

        name = enriched.get("institute_name") or enriched.get("college_name", "")
        code = str(enriched.get("institute_code", ""))
        cache_key = f"{code}_{name}"

        scraped_data = self.cache.get(cache_key)
        if scraped_data is None:
            # Check Master Metrics DB via CollegeMetricsService for instant verified data
            try:
                from scripts.college_metrics_service import CollegeMetricsService
                cms = CollegeMetricsService.get_instance()
                master_metrics = cms.get_metrics_for_code(code)
                if not master_metrics and name:
                    master_metrics = cms.get_or_enrich_college(code, name)
                if master_metrics:
                    f_val = str(master_metrics.get("fee_data", {}).get("total_annual_fee", ""))
                    p_val = str(master_metrics.get("placement_data", {}).get("average_package", ""))
                    src = master_metrics.get("fee_data", {}).get("source_citation", "Official FRA / NIRF Disclosure")
                    scraped_data = {
                        "naac_grade_scraped": master_metrics.get("naac_grade"),
                        "nirf_rank_scraped": master_metrics.get("nirf_rank"),
                        "annual_fee_scraped": f_val,
                        "avg_package_scraped": p_val,
                        "_sources": [src],
                    }
                    self.cache.set(cache_key, scraped_data)
            except Exception as e:
                logger.debug("Master metrics lookup skipped: %s", e)

        if scraped_data is None:
            scraped_data = self.fetch(name, institute_code=code)
            self.cache.set(cache_key, scraped_data)

        field_mapping = {
            "naac_grade": "naac_grade_scraped",
            "nirf_rank": "nirf_rank_scraped",
            "established_year": "established_scraped",
            "affiliation": "affiliation_scraped",
            "annual_fee": "annual_fee_scraped",
            "avg_package": "avg_package_scraped",
        }

        for target in missing_fields:
            scraped_k = field_mapping.get(target)
            if scraped_k and scraped_data.get(scraped_k):
                val = scraped_data[scraped_k]
                source_urls = scraped_data.get("_sources", ["secondary_web"])
                src = source_urls[0] if source_urls else "secondary_web"

                sc_field = ScrapedField(
                    field_name=target,
                    value=val,
                    source_url=src,
                    publisher="Secondary Web Directory",
                    retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                    academic_or_placement_year="2024-25",
                    extraction_method="regex_pattern",
                    verification_status="secondary_unverified",
                    field_scope="college_level",
                    is_primary_source=False,
                )
                enriched[target] = val
                scraped_fields_provenance[target] = sc_field.to_dict()

        return enriched
