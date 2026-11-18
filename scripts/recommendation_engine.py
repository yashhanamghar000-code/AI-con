"""
College Comparison and Recommendation Engine (AI-con Task 7)
------------------------------------------------------------
Evaluates college choices against student scores, verified eligibility, and historical
cutoff evidence using deterministic, transparent heuristics.

Key Principles (AI_CON_IMPROVEMENT_PLAN.md Task 7):
1. No False Guarantees: An entrance score higher than a past cutoff does NOT guarantee
   admission. Predictions are strictly framed as historical observations.
2. No Fabricated Probabilities: Never assign pseudo-scientific probabilities (e.g. '92% chance').
3. Transparent Classification Tiers (Standardized Canonical Labels with dual string equality):
   - "ineligible" / "Ineligible"
   - "eligibility_unresolved" / "Eligibility Unresolved"
   - "insufficient_evidence" / "Insufficient evidence"
   - "reach" / "Reach"
   - "competitive" / "Competitive"
   - "historically_more_attainable" / "Historically more attainable"
4. Configurable Heuristics:
   - Percentile delta: >= +2.0 (historically_more_attainable), <= -2.5 (reach), else (competitive).
   - Rank delta: student <= 0.85 * cutoff_rank (historically_more_attainable),
                 student > 1.15 * cutoff_rank (reach), else (competitive).
5. Exact Metric Separation:
   - Compares percentile with closing_percentile only.
   - Compares rank with closing_rank only.
   - Margin is explicitly explained in rationale.
6. Deterministic Record Selection:
   - Does not blindly pick results[0]. Filters explicitly by category, academic year, and round.
   - Sorts deterministically by round descending, stage ascending, and closing percentile descending.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
AGENTS_DIR = SCRIPTS_DIR / "agents"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from admission_rules import AdmissionRulesEngine, StudentProfile  # noqa: E402
from cutoff_agent import CutoffAgent  # noqa: E402


class RecommendationTier(str, Enum):
    """
    Standard canonical recommendation tiers per Task 7 specification.
    Dual-compatibility: matches both snake_case ('historically_more_attainable')
    and Title Case ('Historically more attainable').
    """
    INELIGIBLE = "Ineligible"
    ELIGIBILITY_UNRESOLVED = "Eligibility Unresolved"
    INSUFFICIENT_EVIDENCE = "Insufficient evidence"
    REACH = "Reach"
    COMPETITIVE = "Competitive"
    HISTORICALLY_MORE_ATTAINABLE = "Historically more attainable"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            s_norm = self.value.lower().replace(" ", "_").replace("-", "_")
            o_norm = other.lower().replace(" ", "_").replace("-", "_")
            return s_norm == o_norm or self.value == other
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.value)

    @property
    def canonical_name(self) -> str:
        return self.value.lower().replace(" ", "_")

    @property
    def display_name(self) -> str:
        return self.value


@dataclass
class RecommendationThresholds:
    """Configurable heuristics for categorizing historical competitiveness."""
    percentile_attainable_delta: float = 2.0   # student >= cutoff + 2.0
    percentile_reach_delta: float = -2.5       # student <= cutoff - 2.5
    rank_attainable_ratio: float = 0.85        # student_rank <= cutoff_rank * 0.85 (lower is better)
    rank_reach_ratio: float = 1.15             # student_rank > cutoff_rank * 1.15


class RecommendationEngine:
    """Provides deterministic comparison and evaluation of candidate college options."""

    def __init__(
        self,
        cutoff_agent: CutoffAgent,
        rules_engine: Optional[AdmissionRulesEngine] = None,
        thresholds: Optional[RecommendationThresholds] = None,
    ):
        self.cutoff_agent = cutoff_agent
        self.rules_engine = rules_engine or AdmissionRulesEngine()
        self.thresholds = thresholds or RecommendationThresholds()

    def _select_best_cutoff_record(
        self,
        records: List[Dict[str, Any]],
        target_round: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Deterministically select the most relevant cutoff record without arbitrary results[0].
        
        Sorting hierarchy:
        1. Exact round match if requested, else highest round available (Round 3 > Round 2 > Round 1)
        2. Stage 1 before Stage 2
        3. Highest closing percentile / best rank
        """
        if not records:
            return None

        def sort_key(r: Dict[str, Any]) -> Tuple[int, int, float]:
            round_val = int(r.get("round") or 1)
            # If target round specified, rank exact matches highest
            round_match_score = 1 if (target_round is not None and round_val == target_round) else 0
            # Stages: stage 1 preferred
            stage_str = str(r.get("stage", "1")).strip()
            stage_val = int(stage_str) if stage_str.isdigit() else 1
            # Closing percentile as secondary deterministic tie-breaker
            cp = float(r.get("closing_percentile") or 0.0)
            return (round_match_score, round_val, -stage_val, cp)

        sorted_records = sorted(records, key=sort_key, reverse=True)
        return sorted_records[0]

    def compare_colleges(
        self,
        institute_codes: List[str],
        branch: str,
        category: str,
        academic_year: str = "2023-24",
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
            m = self._select_best_cutoff_record(results, target_round=round_no)
            if m:
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
        specific_category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate an individual college/branch choice for a candidate student.
        
        Returns standardized dictionary with:
        - canonical tier (Ineligible, Eligibility Unresolved, Insufficient evidence,
                          Reach, Competitive, Historically more attainable)
        - exact margin calculation and rationale
        - no false promises or fabricated probability numbers
        """
        code_str = str(institute_code).strip()

        # 1. Eligibility Check (isolated from cutoff competitiveness)
        elig = self.rules_engine.evaluate_student(student)
        if elig.status == "ineligible":
            return {
                "institute_code": code_str,
                "institute_name": None,
                "branch": branch,
                "tier": RecommendationTier.INELIGIBLE,
                "tier_canonical": RecommendationTier.INELIGIBLE.canonical_name,
                "tier_display": RecommendationTier.INELIGIBLE.display_name,
                "eligible": False,
                "reason": "; ".join(elig.explanations) if elig.explanations else "Candidate does not meet statutory CET eligibility criteria.",
                "evidence": None,
                "disclaimer": "Statutory eligibility rules supersede historical cutoff positions.",
            }

        # 2. Year Resolution
        years_avail = self.cutoff_agent.years_available(code_str)
        if not years_avail:
            return {
                "institute_code": code_str,
                "institute_name": None,
                "branch": branch,
                "tier": RecommendationTier.INSUFFICIENT_EVIDENCE,
                "tier_canonical": RecommendationTier.INSUFFICIENT_EVIDENCE.canonical_name,
                "tier_display": RecommendationTier.INSUFFICIENT_EVIDENCE.display_name,
                "eligible": elig.status == "eligible",
                "reason": f"No historical cutoff records available for institute {code_str}.",
                "evidence": None,
                "disclaimer": "Historical observations describe past rounds only and are not admission guarantees.",
            }

        eval_year = target_year if (target_year and target_year in years_avail) else sorted(years_avail)[-1]

        # 3. Determine Candidate Categories to Check
        # If student explicitly requests a category they are legally ineligible for under CET rules:
        if specific_category:
            req_cat = specific_category.upper()
            if req_cat not in elig.applicable_categories:
                return {
                    "institute_code": code_str,
                    "institute_name": None,
                    "branch": branch,
                    "tier": RecommendationTier.INELIGIBLE,
                    "tier_canonical": RecommendationTier.INELIGIBLE.canonical_name,
                    "tier_display": RecommendationTier.INELIGIBLE.display_name,
                    "eligible": False,
                    "reason": f"Candidate does not qualify for requested quota '{req_cat}' under Maharashtra CET rules (Applicable: {elig.applicable_categories}).",
                    "evidence": None,
                    "disclaimer": "Statutory eligibility rules supersede historical cutoff positions.",
                }
            search_categories = [req_cat]
        elif elig.applicable_categories:
            search_categories = list(elig.applicable_categories)
        else:
            search_categories = ["GOPENS"]

        best_match: Optional[Dict[str, Any]] = None
        for cat in search_categories:
            matches = self.cutoff_agent.get_cutoffs(
                code_str,
                year=eval_year,
                branch_query=branch,
                category=cat,
                round_no=round_no,
            )
            if matches:
                best_match = self._select_best_cutoff_record(matches, target_round=round_no)
                if best_match:
                    break

        # If no record at exact round, attempt any round for transparent reporting
        if not best_match:
            for cat in search_categories:
                matches_any_round = self.cutoff_agent.get_cutoffs(
                    code_str,
                    year=eval_year,
                    branch_query=branch,
                    category=cat,
                )
                if matches_any_round:
                    best_match = self._select_best_cutoff_record(matches_any_round)
                    if best_match:
                        break

        if not best_match:
            return {
                "institute_code": code_str,
                "institute_name": None,
                "branch": branch,
                "academic_year": eval_year,
                "tier": RecommendationTier.INSUFFICIENT_EVIDENCE,
                "tier_canonical": RecommendationTier.INSUFFICIENT_EVIDENCE.canonical_name,
                "tier_display": RecommendationTier.INSUFFICIENT_EVIDENCE.display_name,
                "eligible": elig.status == "eligible",
                "reason": f"No historical cutoffs found for branch '{branch}' under candidate quota(s) {search_categories} in {eval_year}.",
                "evidence": None,
                "disclaimer": "Historical observations describe past rounds only and are not admission guarantees.",
            }

        c_rank = best_match.get("closing_rank")
        c_perc = best_match.get("closing_percentile")
        actual_round = best_match.get("round", round_no)

        # 4. Check for Unresolved Profile (score missing)
        if student.percentile is None and student.merit_rank is None:
            return {
                "institute_code": code_str,
                "institute_name": best_match.get("institute_name"),
                "branch": best_match.get("branch"),
                "category_applied": best_match.get("category"),
                "academic_year": eval_year,
                "round": actual_round,
                "closing_rank": c_rank,
                "closing_percentile": c_perc,
                "tier": RecommendationTier.ELIGIBILITY_UNRESOLVED,
                "tier_canonical": RecommendationTier.ELIGIBILITY_UNRESOLVED.canonical_name,
                "tier_display": RecommendationTier.ELIGIBILITY_UNRESOLVED.display_name,
                "eligible": elig.status == "eligible",
                "reason": "Candidate has not provided MHT-CET percentile or merit rank. Comparison cannot be computed.",
                "evidence_id": best_match.get("evidence_id"),
                "disclaimer": "Historical observations describe past rounds only and are not admission guarantees.",
            }

        # 5. Competitiveness Classification (Strict Separation of Metrics)
        tier = RecommendationTier.COMPETITIVE
        margin_explained = ""
        metric_used = ""
        student_metric_val = None
        cutoff_metric_val = None

        if student.percentile is not None and c_perc is not None:
            metric_used = "percentile"
            student_metric_val = float(student.percentile)
            cutoff_metric_val = float(c_perc)
            delta = student_metric_val - cutoff_metric_val

            if delta >= self.thresholds.percentile_attainable_delta:
                tier = RecommendationTier.HISTORICALLY_MORE_ATTAINABLE
                margin_explained = (
                    f"Student percentile ({student_metric_val:.4f}) exceeded historical Round {actual_round} "
                    f"closing cutoff ({cutoff_metric_val:.4f}) by +{delta:.2f} points in {eval_year}."
                )
            elif delta <= self.thresholds.percentile_reach_delta:
                tier = RecommendationTier.REACH
                margin_explained = (
                    f"Historical Round {actual_round} closing cutoff ({cutoff_metric_val:.4f}) in {eval_year} was "
                    f"higher than student percentile ({student_metric_val:.4f}) by {abs(delta):.2f} points."
                )
            else:
                tier = RecommendationTier.COMPETITIVE
                margin_explained = (
                    f"Student percentile ({student_metric_val:.4f}) is closely competitive with historical "
                    f"Round {actual_round} closing cutoff ({cutoff_metric_val:.4f}) in {eval_year} (margin: {delta:+.2f})."
                )

        elif student.merit_rank is not None and c_rank is not None:
            metric_used = "merit_rank"
            student_metric_val = int(student.merit_rank)
            cutoff_metric_val = int(c_rank)
            # Merit rank logic: lower rank number = better rank
            rank_margin = cutoff_metric_val - student_metric_val  # positive means student has better rank

            if student_metric_val <= int(cutoff_metric_val * self.thresholds.rank_attainable_ratio):
                tier = RecommendationTier.HISTORICALLY_MORE_ATTAINABLE
                margin_explained = (
                    f"Student merit rank (#{student_metric_val:,}) was comfortably within historical Round {actual_round} "
                    f"closing rank (#{cutoff_metric_val:,}) in {eval_year} (margin: +{rank_margin:,} ranks)."
                )
            elif student_metric_val > int(cutoff_metric_val * self.thresholds.rank_reach_ratio):
                tier = RecommendationTier.REACH
                margin_explained = (
                    f"Historical Round {actual_round} closing rank (#{cutoff_metric_val:,}) in {eval_year} was ahead of "
                    f"student merit rank (#{student_metric_val:,}) by {abs(rank_margin):,} ranks."
                )
            else:
                tier = RecommendationTier.COMPETITIVE
                margin_explained = (
                    f"Student merit rank (#{student_metric_val:,}) is within 15% range of historical Round {actual_round} "
                    f"closing rank (#{cutoff_metric_val:,}) in {eval_year} (margin: {rank_margin:+,} ranks)."
                )
        else:
            tier = RecommendationTier.INSUFFICIENT_EVIDENCE
            margin_explained = (
                "Candidate score metric could not be matched directly against historical cutoff metric "
                "(one party had rank only while the other had percentile only)."
            )

        # 6. Flag if specific category verification is required
        # Note: If category applied was successfully matched and student has score,
        # missing general profile fields like home_university do not block State Level (GOPENS) categorization.
        # Only override tier if the specific category requested has unverified documentation.
        applied_cat = best_match.get("category", "")
        cat_needs_verification = False
        if "has_caste_validity" in elig.missing_fields and any(c in applied_cat for c in ("OBC", "SC", "ST", "VJ", "NT")):
            cat_needs_verification = True
        elif "has_non_creamy_layer" in elig.missing_fields and any(c in applied_cat for c in ("OBC", "SBC", "VJ", "NT")):
            cat_needs_verification = True
        elif "has_ews_certificate" in elig.missing_fields and "EWS" in applied_cat:
            cat_needs_verification = True
        elif "annual_income" in elig.missing_fields and "TFWS" in applied_cat:
            cat_needs_verification = True

        if cat_needs_verification:
            tier = RecommendationTier.ELIGIBILITY_UNRESOLVED
            margin_explained += f" Note: Quota documentation requires verification of {elig.missing_fields}."
        elif elig.status == "needs_verification" and elig.missing_fields:
            margin_explained += f" Note: Candidate profile has pending fields: {elig.missing_fields}."

        return {
            "institute_code": code_str,
            "institute_name": best_match.get("institute_name"),
            "branch": best_match.get("branch"),
            "category_applied": best_match.get("category"),
            "academic_year": eval_year,
            "round": actual_round,
            "closing_rank": c_rank,
            "closing_percentile": c_perc,
            "tier": tier,
            "tier_canonical": tier.canonical_name,
            "tier_display": tier.display_name,
            "eligible": elig.status != "ineligible",
            "metric_used": metric_used,
            "student_metric_val": student_metric_val,
            "cutoff_metric_val": cutoff_metric_val,
            "margin_explanation": margin_explained,
            "rationale": margin_explained,  # backward compatibility
            "evidence_id": best_match.get("evidence_id"),
            "disclaimer": (
                "Historical comparisons reflect past admission cutoffs under State CET Cell CAP rounds. "
                "Cutoff thresholds vary each year with candidate volume and seat matrix changes; "
                "no past cutoff guarantees future admission or seat allotment."
            ),
        }
