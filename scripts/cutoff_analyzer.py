"""
Historical Cutoff Analysis Service (AI-con Phase 3.3)
-----------------------------------------------------
Provides deterministic analytical calculations over validated historical cutoff records.

Core Principles:
1. Metric Independence: Closing Rank (integer merit number) and Closing Percentile (float score)
   are fundamentally separate measurements and are NEVER mathematically merged, added, or subtracted.
2. Comparability Guardrails: Multi-year or multi-round comparisons require exact alignment on:
   - Institute Code
   - Branch / Course
   - Quota Category token
   - List Type (CAP vs All India)
   - Allocation Stage ("1", "2")
   If records differ on any dimension, the comparison flags comparable=False and provides rationale.
3. No Interpolation / Hallucination: Missing years or missing categories are returned as missing facts.
4. Non-Predictive: Historical increases/decreases are documented as past observations only,
   never as guarantees or promises for future counselling rounds.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
AGENTS_DIR = SCRIPTS_DIR / "agents"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from cutoff_agent import CutoffAgent, canonical_list_type  # noqa: E402


class ShiftDict(dict):
    """Dictionary for multi-year shifts.

    Primary keys use the readable 'YYYY-YY -> YYYY-YY' format, but also supports
    legacy lookups without spaces ('YYYY-YY->YYYY-YY') for seamless compatibility.
    """

    def __getitem__(self, key: Any) -> Any:
        if super().__contains__(key):
            return super().__getitem__(key)
        if isinstance(key, str) and "->" in key:
            alt = key.replace("->", " -> ") if " -> " not in key else key.replace(" -> ", "->")
            if super().__contains__(alt):
                return super().__getitem__(alt)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        if super().__contains__(key):
            return True
        if isinstance(key, str) and "->" in key:
            alt = key.replace("->", " -> ") if " -> " not in key else key.replace(" -> ", "->")
            return super().__contains__(alt)
        return False

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class CutoffAnalyzer:
    """Analytical service for multi-year and multi-round cutoff examination."""

    def __init__(self, cutoff_source: Union[CutoffAgent, Any, str, Path]):
        if isinstance(cutoff_source, CutoffAgent) or hasattr(cutoff_source, "get_cutoffs"):
            self.agent = cutoff_source
        elif isinstance(cutoff_source, (str, Path)):
            self.agent = CutoffAgent(cutoff_source)
        else:
            raise TypeError(
                f"cutoff_source must be a CutoffAgent, an object implementing get_cutoffs, or a Path/str directory, got {type(cutoff_source).__name__}"
            )

    @staticmethod
    def check_comparability(rec_a: Dict[str, Any], rec_b: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Verify that two cutoff records can be legitimately compared."""
        if rec_a.get("institute_code") != rec_b.get("institute_code"):
            return False, "Different institutes cannot be directly compared on baseline trend."
        if (rec_a.get("branch") or "").lower() != (rec_b.get("branch") or "").lower():
            return False, f"Branches differ: '{rec_a.get('branch')}' vs '{rec_b.get('branch')}'."
        if (rec_a.get("category") or "").upper() != (rec_b.get("category") or "").upper():
            return False, f"Categories differ: '{rec_a.get('category')}' vs '{rec_b.get('category')}'."
        if canonical_list_type(rec_a.get("list_type")) != canonical_list_type(rec_b.get("list_type")):
            return False, f"List types differ: '{rec_a.get('list_type')}' vs '{rec_b.get('list_type')}'."
        if str(rec_a.get("stage", "1")) != str(rec_b.get("stage", "1")):
            return False, f"Allotment stages differ: Stage {rec_a.get('stage')} vs Stage {rec_b.get('stage')}."
        return True, None

    def compare_across_years(
        self,
        institute_code: Union[str, int],
        branch: str,
        category: str,
        round_no: int = 1,
        list_type: str = "CAP",
        stage: str = "1",
    ) -> Dict[str, Any]:
        """Compute multi-year trend for a specific (college, branch, category, round) combination."""
        years = self.agent.years_available(institute_code)
        history: List[Dict[str, Any]] = []

        for y in sorted(years):
            matches = self.agent.get_cutoffs(
                institute_code,
                year=y,
                branch_query=branch,
                category=category,
                round_no=round_no,
            )
            target_lt = canonical_list_type(list_type)
            for m in matches:
                # Filter by canonical list_type and stage
                if canonical_list_type(m.get("list_type")) == target_lt and str(m.get("stage", "1")) == str(stage):
                    history.append(m)
                    break

        if not history:
            return {
                "status": "unavailable",
                "comparable": False,
                "message": (
                    f"No matching historical records found for {institute_code} - "
                    f"{branch} - {category} (Round {round_no})."
                ),
                "years_found": [],
                "rank_history": {},
                "percentile_history": {},
            }

        # Validate comparability across chronological records
        for i in range(len(history) - 1):
            comp, reason = self.check_comparability(history[i], history[i + 1])
            if not comp:
                return {
                    "status": "incomparable",
                    "comparable": False,
                    "message": f"Historical records across years are not comparable: {reason}",
                    "years_found": [h["academic_year"] for h in history],
                }

        rank_history = {h["academic_year"]: h["closing_rank"] for h in history if h.get("closing_rank") is not None}
        perc_history = {h["academic_year"]: h["closing_percentile"] for h in history if h.get("closing_percentile") is not None}

        # Calculate rank and percentile shifts
        year_keys = sorted(rank_history.keys())
        rank_deltas: Dict[str, int] = ShiftDict()
        perc_deltas: Dict[str, float] = ShiftDict()

        for i in range(len(year_keys) - 1):
            prev_y, curr_y = year_keys[i], year_keys[i + 1]
            pair_key = f"{prev_y} -> {curr_y}"
            rank_deltas[pair_key] = rank_history[curr_y] - rank_history[prev_y]
            if prev_y in perc_history and curr_y in perc_history:
                perc_deltas[pair_key] = round(perc_history[curr_y] - perc_history[prev_y], 7)

        return {
            "status": "available",
            "comparable": True,
            "institute_code": str(institute_code),
            "institute_name": history[0].get("institute_name"),
            "branch": branch,
            "category": category,
            "round": round_no,
            "list_type": list_type,
            "stage": stage,
            "years_tracked": year_keys,
            "rank_history": rank_history,
            "percentile_history": perc_history,
            "rank_deltas": rank_deltas,
            "percentile_deltas": perc_deltas,
            "evidence_ids": [h.get("evidence_id") for h in history],
            "disclaimer": (
                "Historical observations describe past CAP rounds only. "
                "Cutoff shifts reflect previous batch competition and do not guarantee future round outcomes."
            ),
        }

    def compare_rounds(
        self,
        institute_code: Union[str, int],
        branch: str,
        category: str,
        year: str,
        list_type: str = "CAP",
    ) -> Dict[str, Any]:
        """Track progression across CAP rounds (Round 1 -> 2 -> 3) within a single academic cycle."""
        matches = self.agent.get_cutoffs(
            institute_code,
            year=year,
            branch_query=branch,
            category=category,
        )
        target_lt = canonical_list_type(list_type)
        filtered = [
            m for m in matches
            if canonical_list_type(m.get("list_type")) == target_lt
        ]

        if not filtered:
            return {
                "status": "unavailable",
                "message": f"No records found for {institute_code} in year {year} across rounds.",
                "rounds": {},
            }

        # Group by round number
        by_round: Dict[int, Dict[str, Any]] = {}
        for m in sorted(filtered, key=lambda x: x.get("round", 1)):
            rnd = m.get("round", 1)
            if rnd not in by_round:
                by_round[rnd] = m

        round_keys = sorted(by_round.keys())
        round_ranks = {r: by_round[r].get("closing_rank") for r in round_keys}
        round_percs = {r: by_round[r].get("closing_percentile") for r in round_keys}

        return {
            "status": "available",
            "institute_code": str(institute_code),
            "institute_name": filtered[0].get("institute_name"),
            "branch": branch,
            "category": category,
            "academic_year": year,
            "list_type": list_type,
            "rounds_available": round_keys,
            "round_ranks": round_ranks,
            "round_percentiles": round_percs,
            "evidence_ids": [by_round[r].get("evidence_id") for r in round_keys],
        }

    def get_data_coverage_summary(self, institute_code: Union[str, int]) -> Dict[str, Any]:
        """Summarize data availability for an institute across years, branches, and categories."""
        code_str = str(institute_code).strip()
        years = self.agent.years_available(code_str)
        branches = self.agent.list_branches(code_str)

        total_cutoffs = 0
        categories_found: set = set()

        for y in years:
            for b in branches:
                res = self.agent.get_cutoffs(code_str, year=y, branch_query=b)
                total_cutoffs += len(res)
                for r in res:
                    if r.get("category"):
                        categories_found.add(r["category"])

        return {
            "institute_code": code_str,
            "years_available": years,
            "branch_count": len(branches),
            "branches": branches,
            "category_count": len(categories_found),
            "categories": sorted(categories_found),
            "total_cutoffs_recorded": total_cutoffs,
        }
