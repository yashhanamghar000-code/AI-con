#!/usr/bin/env python3
"""
AI-CON Interactive Terminal Console
Allows users to ask custom questions directly against:
1. Cutoff Database (Exact Historical Grounding across years 2020-2026)
2. Option Form / College Finder (Multi-College search by percentile/rank)
3. Tabular ML Prediction Models (Closing Rank & Percentile regressors)
4. College Qualitative Profiles (Vector RAG)
5. Anti-Hallucination Guardrails & Verified Citations
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
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
            "message": f"No colleges found matching branch '{branch_query}' and category '{cat_upper}'.",
        }

    # Categorize into official CAP Strategy Tiers
    reach: List[Dict[str, Any]] = []
    competitive: List[Dict[str, Any]] = []
    attainable: List[Dict[str, Any]] = []

    if is_rank:
        # For rank, lower number is better
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
        # For percentile, higher score is better
        # Candidate has 88 percentile
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

def print_banner():
    print("=" * 76)
    print(">> AI-CON: Maharashtra Engineering Admissions AI Counselling System <<")
    print("=" * 76)
    print("Modes Supported:")
    print("  * Option Form / College Discovery (e.g. 'Colleges for my 88 percentile Mechanical GOPENS')")
    print("  * Exact Cutoffs & Multi-Year Trends (e.g. 'COEP Computer Engineering GOPENS')")
    print("  * College Qualitative Facts (e.g. 'What is the affiliation of VJTI Mumbai?')")
    print("  * ML Cutoff Predictions (Predict closing rank & percentile)")
    print("  * Anti-Hallucination Guardrails & Verified Citations")
    print("Type 'exit', 'quit', or 'q' to stop.")
    print("=" * 76)

def run_interactive_terminal():
    print_banner()

    print("\n[1/3] Initializing Cutoff Agent...")
    cutoff_agent = None
    if CUTOFFS_DIR.exists():
        cutoff_agent = CutoffAgent(str(CUTOFFS_DIR))
        print(f"  [OK] Cutoffs loaded from: {CUTOFFS_DIR}")
    else:
        print("  [--] Cutoff directory not found.")

    print("\n[2/3] Initializing Vector Store (College Info)...")
    info_agent = None
    if VECTOR_INDEX_DIR.exists() and CollegeInfoAgent is not None:
        try:
            info_agent = CollegeInfoAgent(str(VECTOR_INDEX_DIR))
            print(f"  [OK] Vector index connected from: {VECTOR_INDEX_DIR}")
        except (Exception, SystemExit):
            print("  [--] Vector agent bypassed (running in exact cutoff & ML mode).")
    else:
        print("  [--] Vector agent bypassed (running in exact cutoff & ML mode).")

    print("\n[3/3] Initializing Orchestrator Pipeline...")
    orch = Orchestrator(cutoff_agent, info_agent, llm_call=None)

    # Web Scraper Cache — fallback when local data is missing
    web_cache = None
    if WebScraperCache is not None and VECTOR_INDEX_DIR.exists():
        try:
            web_cache = WebScraperCache(vector_index_path=str(VECTOR_INDEX_DIR))
            stats = web_cache.stats()
            print(f"  [OK] Web Scraper Cache ready (ChromaDB: {stats.get('total_docs', 0)} docs, "
                  f"{stats.get('web_scraped_docs', 0)} previously scraped).")
        except Exception as _wce:
            print(f"  [--] Web Scraper Cache unavailable: {_wce}")
            web_cache = None
    else:
        print("  [--] Web Scraper Cache bypassed (ChromaDB or WebScraperCache not available).")

    has_ml = load_tabular_models()
    if has_ml:
        print("  [OK] Tabular ML Regressor Models ready.")

    print("\n" + "-" * 76)
    print("Ready for your queries! You can ask anything about Maharashtra engineering colleges.")
    print("-" * 76)

    while True:
        try:
            query = input("\n[AI-CON] Enter your question > ").strip()
            if not query:
                continue
            if query.lower() in ("exit", "quit", "q"):
                print("\nExiting AI-CON. Thank you!")
                break

            print("\nProcessing query...")

            # Clean bullet points if pasted from prompts
            clean_q = re.sub(r"^[\s\u2022\*\-]+", "", query).strip()

            # CHECK 1: Is this an Option Form / Multi-College discovery query?
            score, is_rank, branch, cat = extract_score_and_criteria(clean_q)
            is_discovery = any(kw in clean_q.lower() for kw in [
                "every college", "all colleges", "which college", "what college",
                "list of colleges", "option form", "preference list", "within the",
                "where my", "get admission", "my chances", "eligible colleges", "find college"
            ])

            if score is not None and (is_discovery or branch):
                print(f"\n--- CAP Option Form & College Discovery ---")
                metric_name = "Rank" if is_rank else "Percentile"
                print(f"Target: {metric_name} = {score} | Branch: {branch or 'All'} | Category: {cat}")

                plan = find_colleges_for_score(
                    cutoff_agent,
                    score=score,
                    is_rank=is_rank,
                    branch_query=branch,
                    category=cat,
                )

                if plan.get("status") == "not_found":
                    print(f"\n[Notice]: {plan['message']}")
                    continue

                attainable = plan.get("attainable", [])
                competitive = plan.get("competitive", [])
                reach = plan.get("reach", [])

                print(f"\nTotal colleges offering {branch or 'the requested branch'}: {plan['total_matched']}")

                # 1. Attainable (Safe) Options
                print(f"\n[1] HIGH PROBABILITY / ATTAINABLE CHOICES ({len(attainable)} found):")
                if attainable:
                    print("    (Your score safely exceeds these historical closing cutoffs - Recommended as Safety Backups)")
                    for idx, c in enumerate(attainable[:8], 1):
                        cp = c.get('closing_percentile')
                        cr = c.get('closing_rank')
                        print(f"    {idx}. {c['name']} (Code: {c['code']})")
                        print(f"       Branch: {c['branch']} | Cutoff: {cp}% (Rank {cr}) [Year {c['year']}]")
                    if len(attainable) > 8:
                        print(f"       ... and {len(attainable) - 8} more colleges within your score.")
                else:
                    print("    None found within this range.")

                # 2. Competitive Options
                print(f"\n[2] COMPETITIVE CHOICES ({len(competitive)} found):")
                if competitive:
                    print("    (Historical cutoffs are very close to your score - High-value Target Choices)")
                    for idx, c in enumerate(competitive[:6], 1):
                        cp = c.get('closing_percentile')
                        cr = c.get('closing_rank')
                        print(f"    {idx}. {c['name']} (Code: {c['code']})")
                        print(f"       Branch: {c['branch']} | Cutoff: {cp}% (Rank {cr}) [Year {c['year']}]")
                else:
                    print("    None found.")

                # 3. Reach Options
                print(f"\n[3] REACH / ASPIRATIONAL CHOICES ({len(reach)} found):")
                if reach:
                    print("    (Historical cutoffs higher than your score - Place at top of CAP Option Form)")
                    for idx, c in enumerate(reach[:4], 1):
                        cp = c.get('closing_percentile')
                        cr = c.get('closing_rank')
                        print(f"    {idx}. {c['name']} (Code: {c['code']})")
                        print(f"       Branch: {c['branch']} | Cutoff: {cp}% (Rank {cr}) [Year {c['year']}]")

                continue

            # CHECK 2: Standard College-specific query
            result = orch.answer(clean_q)

            status = result.get("status")
            intent = result.get("intent")

            print(f"\n--- Result ({intent or 'unknown'}, Status: {status}) ---")

            # Matched College & Code
            col_name = result.get("matched_college")
            inst_code = result.get("institute_code")
            if col_name:
                print(f"[College] {col_name} (Institute Code: {inst_code or 'N/A'})")

            # Evidence / Answer
            evidence = result.get("evidence", "")

            # ── Web Scraper Fallback ─────────────────────────────────────────
            # Trigger when:
            #   - evidence is empty / says "No relevant information found"
            #   - AND there is a resolved college name
            #   - AND this is an info-type query (not a cutoff query)
            _no_info = (
                not evidence
                or "No relevant information found" in evidence
                or "not available" in evidence.lower()
                or (intent in ("info", "both") and "COLLEGE INFO EVIDENCE" not in evidence)
            )
            if _no_info and col_name and intent in ("info", "both") and web_cache is not None:
                print(f"\n  [Notice] No local data found for '{col_name}'. Trying web scraper...")
                web_results = web_cache.get_or_fetch(
                    college_name=col_name,
                    institute_code=inst_code,
                )
                if web_results:
                    web_texts = []
                    for wr in web_results:
                        meta = wr.get("metadata", {})
                        sources = meta.get("source_page", "web")
                        web_texts.append(
                            f"[Web Scraped from {sources}]:\n{wr['text']}"
                        )
                    web_evidence = "\n\n".join(web_texts)
                    evidence = web_evidence
                    status = "web_scraped"
                    print("  [OK] Web data fetched and cached in ChromaDB for future queries.")
                else:
                    print("  [Notice] Web scraper returned no data either.")
            # ────────────────────────────────────────────────────────────────

            if evidence:
                print("\n[Retrieved Grounded Evidence]:")
                print(evidence)

            # Written Answer / LLM Response if available
            if result.get("answer"):
                print("\n[AI-CON Response]:")
                print(result["answer"])

            # Notice / Abstention
            if result.get("notice"):
                print(f"\n[Guardrail Notice]: {result['notice']}")

            if result.get("suggested_clarification"):
                print(f"\n[Clarification Needed]: {result['suggested_clarification']}")
            elif result.get("message") and status == "needs_clarification":
                print(f"\n[Clarification Needed]: {result['message']}")

            if result.get("details"):
                print("\n[Details]:", result["details"])

        except (KeyboardInterrupt, EOFError):
            print("\nExiting AI-CON.")
            break
        except Exception as ex:
            print(f"\n[Error processing question]: {ex}")

if __name__ == "__main__":
    run_interactive_terminal()
