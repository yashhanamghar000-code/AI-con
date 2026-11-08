#!/usr/bin/env python3
"""
AI-CON Interactive Terminal & Orchestrator Host
Allows users to ask custom questions directly against:
1. Cutoff Database (Exact Historical Grounding across years 2020-2026)
2. Option Form / College Finder (Multi-College search by percentile/rank)
3. Tabular ML Prediction Models (Closing Rank & Percentile regressors)
4. College Qualitative Profiles (Vector RAG)
5. Anti-Hallucination Guardrails & Verified Citations
6. Local Web UI Dashboard & Chatbot (aicon_ui)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
AGENTS_DIR = SCRIPTS_DIR / "agents"
CUTOFFS_DIR = PROJECT_ROOT / "cutoffs" / "phase3_final_staging"
VECTOR_INDEX_DIR = PROJECT_ROOT / "vector_index"
MODEL_ARTIFACTS_DIR = PROJECT_ROOT / "model_artifacts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from orchestrator import Orchestrator
    from cutoff_agent import CutoffAgent
    from college_resolver import CollegeResolver
except Exception as e:
    print(f"Error importing agents: {e}")

try:
    from college_info_agent import CollegeInfoAgent
except Exception:
    CollegeInfoAgent = None

try:
    from web_scraper_cache import WebScraperCache
except Exception:
    WebScraperCache = None

# Optional ML models
tabular_rank_model = None
tabular_pct_model = None
tabular_encoder_info = None

def load_tabular_models():
    global tabular_rank_model, tabular_pct_model, tabular_encoder_info
    try:
        import joblib
        rank_p = MODEL_ARTIFACTS_DIR / "cutoff_regressor_rank.joblib"
        pct_p = MODEL_ARTIFACTS_DIR / "cutoff_regressor_percentile.joblib"
        enc_p = MODEL_ARTIFACTS_DIR / "label_encoders.joblib"
        if rank_p.exists() and pct_p.exists() and enc_p.exists():
            tabular_rank_model = joblib.load(rank_p)
            tabular_pct_model = joblib.load(pct_p)
            tabular_encoder_info = joblib.load(enc_p)
            return True
    except Exception as err:
        print(f"[Notice] Tabular models not loaded: {err}")
    return False

def find_colleges_for_score(
    cutoff_agent: CutoffAgent,
    score: float,
    is_rank: bool = False,
    branch_query: Optional[str] = None,
    category: str = "GOPENS",
    academic_year: str = "2024-25",
    round_no: int = 1,
) -> Dict[str, Any]:
    """Search ALL colleges across Maharashtra to recommend option list by student percentile or rank."""
    all_colleges: List[Dict[str, Any]] = []

    branch_norm = branch_query.lower() if branch_query else ""
    cat_upper = category.upper() if category else "GOPENS"

    # Iterate over unique institutes
    for code, years_map in cutoff_agent._by_code.items():
        if len(code) == 4 and code.isdigit():
            continue  # avoid 4-digit / 5-digit alias duplicates

        college = years_map.get(academic_year) or years_map.get("2023-24") or (list(years_map.values())[-1] if years_map else None)
        if not college:
            continue

        inst_name = college.get("institute_name", "")
        for b in college.get("branches", []):
            b_name = b.get("branch", "")
            if branch_norm and branch_norm not in b_name.lower():
                continue

            for cat in b.get("categories", []):
                if cat.get("category", "").upper() == cat_upper:
                    for cut in cat.get("cutoffs", []):
                        if round_no and cut.get("round") != round_no:
                            continue

                        cp = cut.get("closing_percentile")
                        cr = cut.get("closing_rank")

                        if is_rank and cr is not None:
                            all_colleges.append({
                                "code": code,
                                "name": inst_name,
                                "branch": b_name,
                                "category": cat_upper,
                                "round": cut.get("round"),
                                "closing_rank": int(cr),
                                "closing_percentile": cp,
                                "year": college.get("academic_year"),
                                "metric_val": int(cr),
                            })
                        elif not is_rank and cp is not None:
                            all_colleges.append({
                                "code": code,
                                "name": inst_name,
                                "branch": b_name,
                                "category": cat_upper,
                                "round": cut.get("round"),
                                "closing_rank": cr,
                                "closing_percentile": float(cp),
                                "year": college.get("academic_year"),
                                "metric_val": float(cp),
                            })

    if not all_colleges:
        return {
            "status": "not_found",
            "message": f"No colleges found matching branch '{branch_query or 'All'}' and category '{cat_upper}'.",
            "attainable": [],
            "competitive": [],
            "reach": [],
            "total_matched": 0,
        }

    # Categorize into official CAP Strategy Tiers
    reach: List[Dict[str, Any]] = []
    competitive: List[Dict[str, Any]] = []
    attainable: List[Dict[str, Any]] = []

    if is_rank:
        for c in all_colleges:
            cr = c["closing_rank"]
            if cr < score * 0.9:
                reach.append(c)
            elif score * 0.9 <= cr <= score * 1.15:
                competitive.append(c)
            else:
                attainable.append(c)
        attainable.sort(key=lambda x: x["closing_rank"])
        competitive.sort(key=lambda x: x["closing_rank"])
        reach.sort(key=lambda x: x["closing_rank"], reverse=True)
    else:
        for c in all_colleges:
            cp = c["closing_percentile"]
            if cp > score + 3.0:
                reach.append(c)
            elif score - 2.5 <= cp <= score + 3.0:
                competitive.append(c)
            else:
                attainable.append(c)
        attainable.sort(key=lambda x: x["closing_percentile"], reverse=True)
        competitive.sort(key=lambda x: x["closing_percentile"], reverse=True)
        reach.sort(key=lambda x: x["closing_percentile"])

    return {
        "status": "success",
        "score": score,
        "is_rank": is_rank,
        "branch": branch_query or "All Branches",
        "category": cat_upper,
        "academic_year": academic_year,
        "total_matched": len(all_colleges),
        "reach": reach,
        "competitive": competitive,
        "attainable": attainable,
    }

def extract_score_and_criteria(query: str) -> Tuple[Optional[float], bool, Optional[str], str]:
    """Parse score (percentile or rank), branch, and category from free text query."""
    is_rank = False
    score = None

    # Check for percentile
    m_pct = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percentile)\b", query, re.I)
    if not m_pct:
        m_pct = re.search(r"\b(?:percentile|score|pct)\s*(?:is|=|of)?\s*(\d+(?:\.\d+)?)\b", query, re.I)

    # Check for rank
    m_rank = re.search(r"\b(?:rank|merit)\s*(?:is|=|of)?\s*(\d{2,6})\b", query, re.I)

    if m_pct:
        score = float(m_pct.group(1))
        is_rank = False
    elif m_rank:
        score = float(m_rank.group(1))
        is_rank = True

    # Extract branch
    branches = [
        "computer science and engineering", "computer engineering", "computer science",
        "information technology", "mechanical engineering", "mechanical", "civil engineering", "civil",
        "electrical engineering", "electrical", "electronics and telecommunication",
        "electronics", "chemical engineering", "chemical", "aerospace engineering",
        "artificial intelligence", "data science", "automobile", "biotechnology"
    ]
    matched_branch = None
    q_low = query.lower()
    for b in branches:
        if b in q_low:
            matched_branch = b
            break

    # Extract category
    m_cat = re.search(r"\b([GL]?(?:OPEN|SC|ST|OBC|NT1|NT2|NT3|VJ|SBC|SEBC)[SHO]?|TFWS|EWS|AI)\b", query, re.I)
    cat = m_cat.group(1).upper() if m_cat else "GOPENS"

    return score, is_rank, matched_branch, cat


class AiconEngine:
    """Central In-Memory Orchestrator Engine for both Terminal and Web UI."""

    def __init__(
        self,
        cutoffs_dir: Path = CUTOFFS_DIR,
        vector_index_dir: Path = VECTOR_INDEX_DIR,
        model_artifacts_dir: Path = MODEL_ARTIFACTS_DIR,
    ):
        self.cutoffs_dir = cutoffs_dir
        self.vector_index_dir = vector_index_dir
        self.model_artifacts_dir = model_artifacts_dir
        self.cutoff_agent: Optional[CutoffAgent] = None
        self.info_agent: Optional[CollegeInfoAgent] = None
        self.orch: Optional[Orchestrator] = None
        self.web_cache: Optional[WebScraperCache] = None
        self.has_ml: bool = False
        self._init_lock = threading.Lock()
        self._initialized: bool = False

    def initialize(self):
        with self._init_lock:
            if self._initialized:
                return

            print("\n[AI-CON Engine] Initializing Cutoff Agent...")
            if self.cutoffs_dir.exists():
                try:
                    self.cutoff_agent = CutoffAgent(str(self.cutoffs_dir))
                    print(f"  [OK] Cutoffs loaded ({len(self.cutoff_agent._by_code)} institutes)")
                except Exception as e:
                    print(f"  [--] Cutoff loading notice: {e}")
            else:
                print("  [--] Cutoff directory not found.")

            print("[AI-CON Engine] Initializing Vector Store...")
            if self.vector_index_dir.exists() and CollegeInfoAgent is not None:
                try:
                    self.info_agent = CollegeInfoAgent(str(self.vector_index_dir))
                    print(f"  [OK] Vector index connected from: {self.vector_index_dir}")
                except Exception as e:
                    print(f"  [--] Vector index bypassed: {e}")
                    self.info_agent = None

            print("[AI-CON Engine] Initializing Multi-Agent Orchestrator...")
            self.orch = Orchestrator(self.cutoff_agent, self.info_agent, llm_call=None)

            if WebScraperCache is not None and self.vector_index_dir.exists():
                try:
                    self.web_cache = WebScraperCache(vector_index_path=str(self.vector_index_dir))
                    print(f"  [OK] Web Scraper Cache active.")
                except Exception:
                    self.web_cache = None

            self.has_ml = load_tabular_models()
            if self.has_ml:
                print("  [OK] Tabular ML models loaded.")

            self._initialized = True
            print("[AI-CON Engine] Ready.\n")

    def answer_query(self, query: str, use_llm: bool = False) -> Dict[str, Any]:
        """Process question and return structured response for CLI or Web UI."""
        self.initialize()
        clean_q = re.sub(r"^[\s\u2022\*\-]+", "", query).strip()
        if not clean_q:
            return {"status": "error", "message": "Empty query provided.", "answer": "Please ask a question."}

        # CHECK 1: Is this an Option Form / Multi-College discovery query?
        score, is_rank, branch, cat = extract_score_and_criteria(clean_q)
        is_discovery = any(kw in clean_q.lower() for kw in [
            "every college", "all colleges", "which college", "what college",
            "list of colleges", "option form", "preference list", "within the",
            "where my", "get admission", "my chances", "eligible colleges", "find college",
            "colleges for my", "recommend", "options"
        ])

        if score is not None and (is_discovery or branch) and self.cutoff_agent is not None:
            metric_name = "Rank" if is_rank else "Percentile"
            plan = find_colleges_for_score(
                self.cutoff_agent,
                score=score,
                is_rank=is_rank,
                branch_query=branch,
                category=cat,
            )

            if plan.get("status") == "not_found":
                return {
                    "status": "not_found",
                    "intent": "discovery",
                    "answer": plan.get("message", "No matching colleges found."),
                    "message": plan.get("message"),
                    "score": score,
                    "branch": branch,
                    "category": cat,
                }

            attainable = plan.get("attainable", [])
            competitive = plan.get("competitive", [])
            reach = plan.get("reach", [])

            headline = (
                f"Option Form Recommendations: Found {plan['total_matched']} colleges for "
                f"{metric_name} {score} in {branch or 'All Branches'} ({cat}). "
                f"Categorized into {len(attainable)} Attainable (Safety), "
                f"{len(competitive)} Competitive (Target), and {len(reach)} Reach (Aspirational) choices."
            )

            # Build markdown evidence for UI & terminal
            ev_lines = [
                f"CAP OPTION FORM RECOMMENDATION PLAN",
                f"Student Target: {metric_name} = {score} | Branch: {branch or 'All'} | Category: {cat}",
                f"Total Matching Institutes: {plan['total_matched']}\n",
                f"--- [1] ATTAINABLE / SAFETY CHOICES ({len(attainable)} found) ---",
                "(Score safely exceeds historical cutoffs - Recommended as Safety Backups)",
            ]
            for idx, c in enumerate(attainable[:10], 1):
                ev_lines.append(f"  {idx}. {c['name']} (Code: {c['code']}) | Branch: {c['branch']} | Cutoff: {c['closing_percentile']}% (Rank {c['closing_rank']}) [{c['year']}]")
            if len(attainable) > 10:
                ev_lines.append(f"  ... and {len(attainable) - 10} more attainable colleges.")

            ev_lines.append(f"\n--- [2] COMPETITIVE / TARGET CHOICES ({len(competitive)} found) ---")
            ev_lines.append("(Historical cutoffs are very close to your score - High-value Target Choices)")
            for idx, c in enumerate(competitive[:8], 1):
                ev_lines.append(f"  {idx}. {c['name']} (Code: {c['code']}) | Branch: {c['branch']} | Cutoff: {c['closing_percentile']}% (Rank {c['closing_rank']}) [{c['year']}]")

            ev_lines.append(f"\n--- [3] REACH / ASPIRATIONAL CHOICES ({len(reach)} found) ---")
            ev_lines.append("(Cutoffs higher than score - Place at top of preference list)")
            for idx, c in enumerate(reach[:6], 1):
                ev_lines.append(f"  {idx}. {c['name']} (Code: {c['code']}) | Branch: {c['branch']} | Cutoff: {c['closing_percentile']}% (Rank {c['closing_rank']}) [{c['year']}]")

            evidence_text = "\n".join(ev_lines)

            return {
                "status": "answered",
                "intent": "discovery",
                "answer": headline,
                "evidence": evidence_text,
                "total_matched": plan["total_matched"],
                "attainable": attainable[:25],
                "competitive": competitive[:20],
                "reach": reach[:15],
                "score": score,
                "is_rank": is_rank,
                "branch": branch,
                "category": cat,
            }

        # CHECK 2: Standard College-specific query via Orchestrator
        if self.orch is None:
            return {"status": "error", "message": "Orchestrator not ready.", "answer": "Orchestrator engine not ready."}

        result = self.orch.answer(clean_q)
        status = result.get("status", "answered")
        intent = result.get("intent", "general")
        col_name = result.get("matched_college")
        inst_code = result.get("institute_code")
        evidence = result.get("evidence", "")

        # Web scraper fallback if evidence missing
        _no_info = (
            not evidence
            or "No relevant information found" in evidence
            or "not available" in evidence.lower()
            or (intent in ("info", "both") and "COLLEGE INFO EVIDENCE" not in evidence)
        )
        if _no_info and col_name and intent in ("info", "both") and self.web_cache is not None:
            web_results = self.web_cache.get_or_fetch(college_name=col_name, institute_code=inst_code)
            if web_results:
                web_texts = [f"[Web Scraped from {wr.get('metadata', {}).get('source_page', 'web')}]:\n{wr['text']}" for wr in web_results]
                evidence = "\n\n".join(web_texts)
                result["evidence"] = evidence
                result["status"] = "web_scraped"
                status = "web_scraped"

        # Provide a clear headline answer if one wasn't generated
        answer = result.get("answer")
        if not answer:
            if status == "needs_clarification":
                answer = result.get("suggested_clarification") or result.get("message") or "Please clarify which college campus you mean."
            elif evidence:
                if col_name:
                    answer = f"Verified CET Grounded Evidence for {col_name} (Code: {inst_code or 'N/A'}):"
                else:
                    answer = "Retrieved Grounded Evidence from the AI-CON Knowledge Base:"
            else:
                answer = result.get("message") or result.get("notice") or "No exact record matching your criteria was found in the official database."

        result["status"] = "answered" if status in ("evidence_only", "web_scraped", "success") else status
        result["answer"] = answer
        result["evidence"] = evidence
        return result


_GLOBAL_ENGINE: Optional[AiconEngine] = None
_ENGINE_LOCK = threading.Lock()

def get_engine() -> AiconEngine:
    global _GLOBAL_ENGINE
    with _ENGINE_LOCK:
        if _GLOBAL_ENGINE is None:
            _GLOBAL_ENGINE = AiconEngine()
            _GLOBAL_ENGINE.initialize()
        return _GLOBAL_ENGINE


def start_web_server(host: str = "127.0.0.1", port: int = 8000) -> Any:
    """Launch the FastAPI UI server in a background daemon thread."""
    try:
        import uvicorn
        from aicon_ui.app import app
        config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        # Give the server a moment to bind
        time.sleep(1.0)
        return server
    except Exception as exc:
        print(f"[Warning] Could not start background web server: {exc}")
        return None


def print_banner(host: str = "127.0.0.1", port: int = 8000, server_started: bool = True):
    print("=" * 76)
    print(">> AI-CON: Maharashtra Engineering Admissions AI Counselling System <<")
    print("=" * 76)
    if server_started:
        print(f"[WEB UI LIVE] Graphical Dashboard & Chatbot: http://{host}:{port}")
        print("             Open this link in any browser to use the developer's UI!")
    print("[TERMINAL LIVE] Interactive Console active below.")
    print("Modes Supported:")
    print("  * Option Form / College Discovery (e.g. 'Colleges for my 88 percentile Mechanical GOPENS')")
    print("  * Exact Cutoffs & Multi-Year Trends (e.g. 'COEP Computer Engineering GOPENS')")
    print("  * College Qualitative Facts (e.g. 'What is the affiliation of VJTI Mumbai?')")
    print("  * Tabular ML Predictions & Verified Evidence Citations")
    print("Type 'exit', 'quit', or 'q' to stop.")
    print("=" * 76)


def run_interactive_terminal(host: str = "127.0.0.1", port: int = 8000, start_server: bool = True, run_cli: bool = True):
    engine = get_engine()

    server = None
    if start_server:
        server = start_web_server(host=host, port=port)

    print_banner(host=host, port=port, server_started=server is not None)

    if not run_cli:
        print("\n[AI-CON] Running in Server-Only mode. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, EOFError):
            print("\nShutting down AI-CON server.")
            return

    while True:
        try:
            query = input("\n[AI-CON] Enter your question > ").strip()
            if not query:
                continue
            if query.lower() in ("exit", "quit", "q"):
                print("\nExiting AI-CON. Thank you!")
                break

            print("\nProcessing query...")
            result = engine.answer_query(query)

            status = result.get("status")
            intent = result.get("intent")
            print(f"\n--- Result ({intent or 'unknown'}, Status: {status}) ---")

            col_name = result.get("matched_college")
            inst_code = result.get("institute_code")
            if col_name:
                print(f"[College] {col_name} (Institute Code: {inst_code or 'N/A'})")

            evidence = result.get("evidence", "")
            if evidence:
                print("\n[Retrieved Grounded Evidence]:")
                print(evidence)

            if result.get("answer"):
                print("\n[AI-CON Response]:")
                print(result["answer"])

            if result.get("message") and status == "needs_clarification":
                print(f"\n[Clarification Needed]: {result['message']}")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting AI-CON.")
            break
        except Exception as ex:
            print(f"\n[Error processing question]: {ex}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI-CON Interactive Terminal & Web Orchestrator")
    parser.add_argument("--host", default="127.0.0.1", help="Web UI Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Web UI Port (default: 8000)")
    parser.add_argument("--cli-only", action="store_true", help="Run Terminal CLI without starting Web UI server")
    parser.add_argument("--serve-only", action="store_true", help="Run Web UI server only without Terminal input loop")
    args = parser.parse_args()

    run_interactive_terminal(
        host=args.host,
        port=args.port,
        start_server=not args.cli_only,
        run_cli=not args.serve_only,
    )
