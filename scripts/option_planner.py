"""
CAP Option-Form Planner (AI-con Task 7)
---------------------------------------
Constructs a balanced, evidence-grounded preference list strategy for Maharashtra
engineering admissions (MHT-CET CAP option form).

Strategic Principles (AI_CON_IMPROVEMENT_PLAN.md Task 7):
1. Balanced Portfolio Structure:
   - Reach Options (Top): Ambitious aspirations. In CAP, if not allotted, candidate drops to next option.
   - Competitive Options (Middle): Strong candidate choices closely matching historical cutoffs.
   - Historically More Attainable Options (Bottom): High-probability safety choices to ensure seat security.
2. Relative Preference Preservation:
   - Within each tier, preserve the student's original input preference order.
   - Never arbitrarily reorder options within a tier without transparent user intent.
3. Zero Silent Omission:
   - Every candidate preference is accounted for.
   - If an option is risky, unresolved, or ineligible, it is reported with full rationale in unplaced_options.
4. Official CAP Disclaimers:
   - Explains that CAP allotment depends on statutory rules, reservation matrix, and the official submission.
   - Never promises a seat or guarantees admission.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from admission_rules import StudentProfile  # noqa: E402
from recommendation_engine import RecommendationEngine, RecommendationTier  # noqa: E402


class OptionFormPlanner:
    """Plans and structures candidate college choices into a strategic CAP preference order."""

    def __init__(self, recommendation_engine: RecommendationEngine):
        self.engine = recommendation_engine

    def build_option_plan(
        self,
        student: StudentProfile,
        preferred_options: List[Dict[str, str]],
        academic_year: Optional[str] = None,
        round_no: int = 1,
        specific_category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a structured option form strategy from candidate preferences.

        Args:
            student: Candidate profile.
            preferred_options: List of dicts, e.g. [{"institute_code": "01002", "branch": "Computer Engineering"}, ...]
            academic_year: Historical reference year for cutoff comparisons.
            round_no: Reference round (default: 1).
            specific_category: Optional explicit quota category override.

        Returns:
            Structured option form plan containing evaluated choices, categorized buckets,
            recommended sequence, and safety warnings.
        """
        evaluated_choices: List[Dict[str, Any]] = []

        for idx, pref in enumerate(preferred_options, start=1):
            code = pref.get("institute_code", "")
            branch = pref.get("branch", "")
            cat = pref.get("category") or specific_category
            eval_res = self.engine.categorize_option(
                student,
                institute_code=code,
                branch=branch,
                target_year=academic_year,
                round_no=round_no,
                specific_category=cat,
            )
            eval_res["user_preference_rank"] = idx
            evaluated_choices.append(eval_res)

        # Categorize into standardized strategic buckets
        reach: List[Dict[str, Any]] = []
        competitive: List[Dict[str, Any]] = []
        attainable: List[Dict[str, Any]] = []
        unresolved: List[Dict[str, Any]] = []
        ineligible: List[Dict[str, Any]] = []

        for choice in evaluated_choices:
            tier = choice.get("tier")
            # Support both canonical enum values and legacy casing
            if tier in (RecommendationTier.REACH.value, "Reach"):
                reach.append(choice)
            elif tier in (RecommendationTier.COMPETITIVE.value, "Competitive"):
                competitive.append(choice)
            elif tier in (RecommendationTier.HISTORICALLY_MORE_ATTAINABLE.value, "Historically more attainable"):
                attainable.append(choice)
            elif tier in (RecommendationTier.INELIGIBLE.value, "Ineligible"):
                ineligible.append(choice)
            else:
                unresolved.append(choice)

        # Construct recommended sequence: Reach -> Competitive -> Historically more attainable
        # Within each tier, preserve the student's relative preference order
        recommended_sequence: List[Dict[str, Any]] = []
        seq_num = 1

        for c in reach:
            c_copy = dict(c)
            c_copy["recommended_position"] = seq_num
            c_copy["position_rationale"] = (
                "Aspirational choice placed at top of option form. "
                "In CAP rounds, if not allotted, candidate consideration seamlessly cascades to the next preference."
            )
            recommended_sequence.append(c_copy)
            seq_num += 1

        for c in competitive:
            c_copy = dict(c)
            c_copy["recommended_position"] = seq_num
            c_copy["position_rationale"] = (
                "Core target choice closely matching historical cutoff range for candidate merit profile."
            )
            recommended_sequence.append(c_copy)
            seq_num += 1

        for c in attainable:
            c_copy = dict(c)
            c_copy["recommended_position"] = seq_num
            c_copy["position_rationale"] = (
                "Historically more attainable safety anchor to guard against round-over-round cutoff shifts."
            )
            recommended_sequence.append(c_copy)
            seq_num += 1

        # Safety & Risk Warnings
        warnings: List[str] = []
        if len(attainable) == 0:
            warnings.append(
                "Risk Alert: No 'Historically More Attainable' options found in preference list. "
                "Consider adding 2-3 backup options where past cutoffs were comfortably below your score "
                "to ensure securing an allotment in Round 1."
            )
        if len(ineligible) > 0:
            warnings.append(
                f"Eligibility Alert: {len(ineligible)} choice(s) disqualify under statutory CET quota/domicile rules. "
                "These options will be rejected or reclassified by the CAP portal during document verification."
            )
        if len(unresolved) > 0:
            warnings.append(
                f"Data Notice: {len(unresolved)} choice(s) lack historical cutoff records or require score/profile verification."
            )

        return {
            "student_profile": {
                "entrance_exam": student.entrance_exam,
                "percentile": student.percentile,
                "merit_rank": student.merit_rank,
                "category": student.caste_category,
                "domicile": student.domicile,
                "home_university": student.home_university,
            },
            "reference_year": academic_year or "Latest Available",
            "reference_round": round_no,
            "total_preferences_submitted": len(preferred_options),
            "tier_counts": {
                "reach": len(reach),
                "competitive": len(competitive),
                "historically_more_attainable": len(attainable),
                "attainable": len(attainable),  # backward compatibility alias
                "unresolved": len(unresolved),
                "ineligible": len(ineligible),
            },
            "recommended_sequence": recommended_sequence,
            "unplaced_options": unresolved + ineligible,
            "warnings": warnings,
            "disclaimer": (
                "This advisory option form plan is generated for strategic preparation only. "
                "It is not an official submission to the State CET Cell CAP portal. "
                "CAP seat allotment is governed strictly by the official Merit List, seat matrix, "
                "and candidate preference sequence submitted during the active CAP window. "
                "Historical cutoffs describe past observations and are never an admission guarantee."
            ),
        }
