#!/usr/bin/env python3
"""
AI-CON Web Scraper Cache (ChromaDB-backed)
==========================================
Layer that sits between the Orchestrator and the live web:

  1. Checks ChromaDB first — if we already scraped a college, return
     the cached result instantly (no network request).
  2. If not found, calls CollegeWebScraper to fetch from the web.
  3. Stores the scraped data back into ChromaDB so future queries are fast.

Usage:
    from web_scraper_cache import WebScraperCache

    cache = WebScraperCache(vector_index_path="./vector_index")
    results = cache.get_or_fetch(college_name="COEP Pune", institute_code="1002")
    # results is a list of CollegeInfoAgent-style dicts:
    # [{"chunk_id": ..., "text": ..., "metadata": {...}, "distance": None}]
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


def _ensure_ef(ef: Any) -> Any:
    """Make an embedding function satisfy ChromaDB's EF protocol."""
    if ef is None:
        return None
    if not hasattr(ef, "name"):
        setattr(ef, "name", lambda: getattr(ef, "__class__").__name__.lower())
    if not hasattr(ef, "default_space"):
        setattr(ef, "default_space", lambda: "cosine")
    if not hasattr(ef, "supported_spaces"):
        setattr(ef, "supported_spaces", lambda: ["cosine", "l2", "ip"])
    if not hasattr(ef, "get_config"):
        setattr(ef, "get_config", lambda: {})
    if not hasattr(ef, "build_from_config"):
        setattr(ef, "build_from_config", lambda cfg: ef)
    return ef


class WebScraperCache:
    """
    ChromaDB-backed cache for web-scraped college data.

    Every time we fetch from the web, we store the result in the same
    ChromaDB collection used by CollegeInfoAgent so all future queries
    against that college benefit from the cached data.
    """

    COLLECTION_NAME = "college_info"

    def __init__(
        self,
        vector_index_path: Union[str, Path],
        model: str = "sentence-transformers/all-MiniLM-L6-v2",
        scraper_delay: float = 1.0,
    ):
        self._path = Path(vector_index_path)
        self._scraper_delay = scraper_delay

        # Lazy-init ChromaDB
        try:
            import chromadb
            from chromadb.utils import embedding_functions
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model)
            ef = _ensure_ef(ef)
            client = chromadb.PersistentClient(path=str(self._path))
            self._collection = client.get_or_create_collection(
                self.COLLECTION_NAME, embedding_function=ef
            )
            logger.info("WebScraperCache: ChromaDB collection ready (%d docs).", self._collection.count())
        except Exception as exc:
            logger.error("WebScraperCache: ChromaDB init failed: %s", exc)
            self._collection = None

        # Lazy-init scraper
        try:
            _scripts = Path(__file__).resolve().parent
            if str(_scripts) not in sys.path:
                sys.path.insert(0, str(_scripts))
            from web_scraper import CollegeWebScraper
            self._scraper = CollegeWebScraper(delay_secs=scraper_delay)
        except ImportError as exc:
            logger.error("WebScraperCache: CollegeWebScraper not available: %s", exc)
            self._scraper = None

    # ──────────────────────────────────────────
    # Cache check helpers
    # ──────────────────────────────────────────

    def _is_cached(self, college_name: str, institute_code: Optional[str] = None) -> bool:
        """Return True if any web-scraped doc for this college exists in ChromaDB."""
        if self._collection is None:
            return False
        try:
            doc_id = self._make_doc_id(college_name, institute_code)
            result = self._collection.get(ids=[doc_id], include=["metadatas"])
            if result and result.get("ids"):
                return True

            # Also search by institute_code filter
            if institute_code:
                res = self._collection.get(
                    where={"institute_code": str(institute_code)}, include=["metadatas"]
                )
                if res and res.get("ids"):
                    return True

            # Try fuzzy match on name
            res = self._collection.get(
                where={"chunk_type": "web_scraped"}, include=["metadatas"]
            )
            for meta in (res.get("metadatas") or []):
                stored = (meta.get("institute_name") or "").lower()
                if stored and college_name.lower() in stored:
                    return True
            return False
        except Exception:
            return False

    def _make_doc_id(self, college_name: str, institute_code: Optional[str] = None) -> str:
        return "WEB_" + re.sub(r"[^A-Za-z0-9]", "_", college_name)[:40] + "_" + (institute_code or "nocode")

    def _load_cached(self, college_name: str, institute_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load already-cached web docs for a college from ChromaDB."""
        if self._collection is None:
            return []

        results: List[Dict[str, Any]] = []

        # Try by generated doc_id
        doc_id = self._make_doc_id(college_name, institute_code)
        try:
            r = self._collection.get(ids=[doc_id], include=["documents", "metadatas"])
            for i, d, m in zip(r.get("ids", []), r.get("documents", []), r.get("metadatas", [])):
                results.append({"chunk_id": i, "text": d, "metadata": m or {}, "distance": None})
        except Exception:
            pass

        # Also try institute_code filter
        if not results and institute_code:
            try:
                r = self._collection.get(
                    where={"institute_code": str(institute_code)},
                    include=["documents", "metadatas"]
                )
                for i, d, m in zip(r.get("ids", []), r.get("documents", []), r.get("metadatas", [])):
                    results.append({"chunk_id": i, "text": d, "metadata": m or {}, "distance": None})
            except Exception:
                pass

        return results

    def _store(self, scraped: Dict[str, Any]) -> bool:
        """Store web-scraped data into ChromaDB. Returns True on success."""
        if self._collection is None or self._scraper is None:
            return False
        try:
            chroma_doc = self._scraper.build_chroma_document(scraped)
            self._collection.upsert(
                ids=[chroma_doc["id"]],
                documents=[chroma_doc["document"]],
                metadatas=[chroma_doc["metadata"]],
            )
            logger.info("WebScraperCache: stored '%s' (id=%s).", scraped.get("college_name"), chroma_doc["id"])
            return True
        except Exception as exc:
            logger.error("WebScraperCache: store failed: %s", exc)
            return False

    # ──────────────────────────────────────────
    # Main public method
    # ──────────────────────────────────────────

    def get_or_fetch(
        self,
        college_name: str,
        institute_code: Optional[str] = None,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return cached college info from ChromaDB, or scrape from the web and cache it.

        Args:
            college_name:   Human-readable college name.
            institute_code: Optional 5-digit MHT-CET institute code.
            force_refresh:  If True, always re-scrape even if cached.

        Returns:
            List of CollegeInfoAgent-style result dicts:
            [{"chunk_id": str, "text": str, "metadata": dict, "distance": None}]
        """
        if not college_name:
            return []

        # 1. Check cache first (unless forced refresh)
        if not force_refresh and self._is_cached(college_name, institute_code):
            cached = self._load_cached(college_name, institute_code)
            if cached:
                logger.info(
                    "WebScraperCache: cache HIT for '%s' (%d docs).",
                    college_name, len(cached)
                )
                return cached

        # 2. Not cached (or force refresh) → scrape from web
        if self._scraper is None:
            logger.warning("WebScraperCache: scraper unavailable, cannot fetch '%s'.", college_name)
            return []

        logger.info("WebScraperCache: cache MISS — scraping web for '%s'...", college_name)
        print(f"\n  [Web Scraper] Fetching live data for '{college_name}' from Shiksha / CollegeDekho / DuckDuckGo...")

        scraped = self._scraper.fetch(college_name, institute_code=institute_code)

        if scraped.get("error"):
            logger.error("WebScraperCache: scrape error: %s", scraped["error"])
            return []

        # 3. Store in ChromaDB for future queries
        self._store(scraped)

        # 4. Return in CollegeInfoAgent result format
        chroma_doc = self._scraper.build_chroma_document(scraped)
        return [{
            "chunk_id": chroma_doc["id"],
            "text":     chroma_doc["document"],
            "metadata": chroma_doc["metadata"],
            "distance": None,
        }]

    def query_scraped(self, query_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Semantic search over ONLY the web-scraped entries in ChromaDB.
        Useful for broad questions that don't target a specific college.
        """
        if self._collection is None or self._collection.count() == 0:
            return []
        try:
            res = self._collection.query(
                query_texts=[query_text],
                n_results=min(n_results, self._collection.count()),
                where={"chunk_type": "web_scraped"},
            )
            out: List[Dict[str, Any]] = []
            ids   = res.get("ids",       [[]])[0]
            docs  = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            dists = res.get("distances", [[]])[0] if res.get("distances") else [None] * len(ids)
            for i, d, m, dist in zip(ids, docs, metas, dists):
                out.append({"chunk_id": i, "text": d, "metadata": m or {}, "distance": dist})
            return out
        except Exception as exc:
            logger.warning("WebScraperCache.query_scraped failed: %s", exc)
            return []

    def stats(self) -> Dict[str, Any]:
        """Return basic stats about the cache."""
        if self._collection is None:
            return {"status": "unavailable"}
        total = self._collection.count()
        try:
            scraped_ids = self._collection.get(
                where={"chunk_type": "web_scraped"}, include=["metadatas"]
            )
            n_scraped = len(scraped_ids.get("ids") or [])
        except Exception:
            n_scraped = 0
        return {
            "status":           "ok",
            "total_docs":       total,
            "web_scraped_docs": n_scraped,
            "path":             str(self._path),
        }
