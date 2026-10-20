"""
CAP Option-Form Planner (AI-con Phase 3.5)
------------------------------------------
Constructs a balanced, evidence-grounded preference list strategy for Maharashtra
engineering admissions (MHT-CET CAP option form).

Strategic Principles:
1. Balanced Portfolio Structure:
   - Reach Options (Top): Ambitious aspirations. In CAP, if not allotted, candidate drops to next option.
   - Competitive Options (Middle): Strong candidate choices aligning with historical median.
   - Attainable Options (Bottom): High-probability safety choices to guarantee securing a seat.
2. Zero Silent Omission: Every candidate preference is accounted for. If an option is risky
   or ineligible, it is reported with full rationale rather than deleted.
3. Official CAP Disclaimer: Clearly marks output as decision-support advice,
   never claiming to be the live CET Cell portal or an admission guarantee.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from admission_rules import StudentProfile  # noqa: E402
from recommendation_engine import RecommendationEngine  # noqa: E402


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
    ) -> Dict[str, Any]:
        """Generate a structured option form strategy from candidate preferences.

        Args:
            student: Candidate profile.
            preferred_options: List of dicts, e.g. [{"institute_code": "01002", "branch": "Computer Engineering"}, ...]
            academic_year: Historical year for comparison.
            round_no: Reference round (default: 1).

        Returns:
            Structured option form plan containing evaluated choices, categorized buckets,
            recommended sequence, and safety warnings.
        """
        evaluated_choices: List[Dict[str, Any]] = []

        for idx, pref in enumerate(preferred_options, start=1):
            code = pref.get("institute_code", "")
            branch = pref.get("branch", "")
            eval_res = self.engine.categorize_option(
                student,
                institute_code=code,
                branch=branch,
                target_year=academic_year,
                round_no=round_no,
            )
            eval_res["user_preference_rank"] = idx
            evaluated_choices.append(eval_res)

        # Categorize into strategic buckets
        reach: List[Dict[str, Any]] = []
        competitive: List[Dict[str, Any]] = []
        attainable: List[Dict[str, Any]] = []
        unresolved: List[Dict[str, Any]] = []
        ineligible: List[Dict[str, Any]] = []

        for choice in evaluated_choices:
            tier = choice.get("tier")
            if tier == "Reach":
                reach.append(choice)
            elif tier == "Competitive":
                competitive.append(choice)
            elif tier == "Historically more attainable":
                attainable.append(choice)
            elif tier == "Ineligible":
                ineligible.append(choice)
            else:
                unresolved.append(choice)

        # Construct recommended sequence: Reach -> Competitive -> Attainable
        # Within each tier, preserve the student's relative preference order
        recommended_sequence: List[Dict[str, Any]] = []
        seq_num = 1

        for c in reach:
            c_copy = dict(c)
            c_copy["recommended_position"] = seq_num
            c_copy["position_rationale"] = "Aspirational option placed early to test higher allotment cutoffs."
            recommended_sequence.append(c_copy)
            seq_num += 1

        for c in competitive:
            c_copy = dict(c)
            c_copy["recommended_position"] = seq_num
            c_copy["position_rationale"] = "Core target option closely matching candidate merit profile."
            recommended_sequence.append(c_copy)
            seq_num += 1

        for c in attainable:
            c_copy = dict(c)
            c_copy["recommended_position"] = seq_num
            c_copy["position_rationale"] = "Safety anchor to guard against round-over-round cutoff spikes."
            recommended_sequence.append(c_copy)
            seq_num += 1

        # Safety & Risk Warnings
        warnings: List[str] = []
        if len(attainable) == 0:
            warnings.append(
                "Risk Alert: No 'Historically more attainable' options found in preference list. "
                "Consider adding 2-3 backup options to ensure an allotment in Round 1."
            )
        if len(ineligible) > 0:
            warnings.append(
                f"Warning: {len(ineligible)} choice(s) disqualify under CET quota rules."
            )
        if len(unresolved) > 0:
            warnings.append(
                f"Notice: {len(unresolved)} choice(s) lack complete historical data or have pending eligibility."
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
                "attainable": len(attainable),
                "unresolved": len(unresolved),
                "ineligible": len(ineligible),
            },
            "recommended_sequence": recommended_sequence,
            "unplaced_options": unresolved + ineligible,
            "warnings": warnings,
            "disclaimer": (
                "This advisory option form plan is generated for strategic preparation. "
                "It is not an official submission to the State CET Cell CAP portal. "
                "Cutoff figures are historical evidence and do not guarantee admission."
            ),
        }
