"""
College Comparison and Recommendation Engine (AI-con Phase 3.4)
---------------------------------------------------------------
Evaluates college choices against student scores, verified eligibility, and historical
cutoff evidence using deterministic, transparent heuristics.

Key Principles:
1. No False Guarantees: An entrance score higher than a past cutoff does NOT guarantee
   admission. Predictions are strictly framed as historical observations.
2. No Fabricated Probabilities: We never assign pseudo-scientific probabilities
   (such as '92% chance of admission') without a validated empirical model.
3. Transparent Classification Tiers:
   - "Historically more attainable": Student score comfortably exceeds past closing metric.
   - "Competitive": Student score is close to historical closing metric.
   - "Reach": Historical closing cutoff was noticeably higher than student score.
   - "Eligibility Unresolved": Incomplete student profile prevents rule validation.
   - "Ineligible": Student legally disqualifies for this quota/track based on CET rules.
   - "Insufficient evidence": No matching historical records exist for comparison.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
AGENTS_DIR = SCRIPTS_DIR / "agents"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from admission_rules import AdmissionRulesEngine, StudentProfile  # noqa: E402
from cutoff_agent import CutoffAgent  # noqa: E402


class RecommendationEngine:
    """Provides deterministic comparison and evaluation of candidate college options."""

    def __init__(
        self,
        cutoff_agent: CutoffAgent,
        rules_engine: Optional[AdmissionRulesEngine] = None,
    ):
        self.cutoff_agent = cutoff_agent
        self.rules_engine = rules_engine or AdmissionRulesEngine()

    def compare_colleges(
        self,
        institute_codes: List[str],
        branch: str,
        category: str,
        academic_year: str = "2024-25",
        round_no: int = 1,
    ) -> Dict[str, Any]:
        """Perform side-by-side comparison of multiple institutes for a specific branch and category."""
        colleges_data: List[Dict[str, Any]] = []

        for code in institute_codes:
            results = self.cutoff_agent.get_cutoffs(
                code,
                year=academic_year,
                branch_query=branch,
                category=category,
                round_no=round_no,
            )
            if results:
                m = results[0]
                colleges_data.append({
                    "institute_code": str(code),
                    "institute_name": m.get("institute_name"),
                    "branch": m.get("branch"),
                    "category": m.get("category"),
                    "round": round_no,
                    "closing_rank": m.get("closing_rank"),
                    "closing_percentile": m.get("closing_percentile"),
                    "evidence_id": m.get("evidence_id"),
                    "has_data": True,
                })
            else:
                colleges_data.append({
                    "institute_code": str(code),
                    "institute_name": None,
                    "branch": branch,
                    "category": category,
                    "round": round_no,
                    "closing_rank": None,
                    "closing_percentile": None,
                    "evidence_id": None,
                    "has_data": False,
                })

        return {
            "academic_year": academic_year,
            "branch": branch,
            "category": category,
            "round": round_no,
            "comparison": colleges_data,
        }

    def categorize_option(
        self,
        student: StudentProfile,
        institute_code: str,
        branch: str,
        target_year: Optional[str] = None,
        round_no: int = 1,
    ) -> Dict[str, Any]:
        """Evaluate an individual college/branch choice for a student candidate."""
        # 1. Eligibility Check
        elig = self.rules_engine.evaluate_student(student)
        if elig.status == "ineligible":
            return {
                "institute_code": str(institute_code),
                "branch": branch,
                "tier": "Ineligible",
                "eligible": False,
                "reason": "; ".join(elig.explanations),
                "evidence": None,
            }

        # 2. Year Resolution
        years_avail = self.cutoff_agent.years_available(institute_code)
        if not years_avail:
            return {
                "institute_code": str(institute_code),
                "branch": branch,
                "tier": "Insufficient evidence",
                "eligible": elig.status == "eligible",
                "reason": f"No historical cutoff records available for institute {institute_code}.",
                "evidence": None,
            }

        eval_year = target_year if target_year in years_avail else sorted(years_avail)[-1]

        # 3. Cutoff Retrieval across student's applicable categories
        best_match: Optional[Dict[str, Any]] = None
        for cat in elig.applicable_categories:
            matches = self.cutoff_agent.get_cutoffs(
                institute_code,
                year=eval_year,
                branch_query=branch,
                category=cat,
                round_no=round_no,
            )
            if matches:
                best_match = matches[0]
                break

        if not best_match:
            return {
                "institute_code": str(institute_code),
                "branch": branch,
                "academic_year": eval_year,
                "tier": "Insufficient evidence",
                "eligible": elig.status == "eligible",
                "reason": f"No historical cutoffs found for branch '{branch}' under applicable quotas {elig.applicable_categories}.",
                "evidence": None,
            }

        c_rank = best_match.get("closing_rank")
        c_perc = best_match.get("closing_percentile")

        # 4. Competitiveness Classification (Strict separation of rank and percentile)
        tier = "Competitive"
        rationale = ""

        if student.percentile is not None and c_perc is not None:
            delta = student.percentile - c_perc
            if delta >= 2.0:
                tier = "Historically more attainable"
                rationale = (
                    f"Student percentile ({student.percentile:.4f}) exceeded historical Round {round_no} "
                    f"cutoff ({c_perc:.4f}) by +{delta:.2f} percentile points in {eval_year}."
                )
            elif delta <= -2.5:
                tier = "Reach"
                rationale = (
                    f"Historical Round {round_no} cutoff ({c_perc:.4f}) in {eval_year} was higher "
                    f"than student percentile ({student.percentile:.4f}) by {abs(delta):.2f} points."
                )
            else:
                tier = "Competitive"
                rationale = (
                    f"Student percentile ({student.percentile:.4f}) is closely competitive with historical "
                    f"Round {round_no} cutoff ({c_perc:.4f}) in {eval_year} (margin: {delta:+.2f})."
                )

        elif student.merit_rank is not None and c_rank is not None:
            # Merit rank logic (lower rank number = better position)
            if student.merit_rank <= int(c_rank * 0.85):
                tier = "Historically more attainable"
                rationale = (
                    f"Student merit rank ({student.merit_rank}) was comfortably within historical closing "
                    f"rank ({c_rank}) in {eval_year}."
                )
            elif student.merit_rank > int(c_rank * 1.15):
                tier = "Reach"
                rationale = (
                    f"Historical closing rank ({c_rank}) in {eval_year} was significantly ahead of "
                    f"student merit rank ({student.merit_rank})."
                )
            else:
                tier = "Competitive"
                rationale = (
                    f"Student merit rank ({student.merit_rank}) is within 15% range of historical closing "
                    f"rank ({c_rank}) in {eval_year}."
                )
        else:
            tier = "Insufficient evidence"
            rationale = "Candidate score metric could not be matched directly against historical cutoff metric."

        if elig.status == "needs_verification":
            tier = "Eligibility Unresolved"
            rationale += f" Note: Eligibility requires verification of {elig.missing_fields}."

        return {
            "institute_code": str(institute_code),
            "institute_name": best_match.get("institute_name"),
            "branch": best_match.get("branch"),
            "category_applied": best_match.get("category"),
            "academic_year": eval_year,
            "round": round_no,
            "closing_rank": c_rank,
            "closing_percentile": c_perc,
            "tier": tier,
            "eligible": elig.status != "ineligible",
            "rationale": rationale,
            "evidence_id": best_match.get("evidence_id"),
            "disclaimer": "Historical observations describe past rounds only and are not admission guarantees.",
        }
