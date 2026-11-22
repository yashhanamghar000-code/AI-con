"""
AI-CON CAP Option Form Blunder Detector & Risk Auditor (Step 4).
Performs static analysis on a candidate's drafted CAP Option Form prior to
official State CET Cell submission to prevent irreversible admission disasters:
  1. Auto-Freeze Disaster on Option #1 (Rule 1).
  2. Inverted Preference Paradox / Cutoff Inversions (Rule 2).
  3. All-Reach Trap / Missing Safety Net (Rule 3).
  4. Invalid DTE 9-Digit Choice Codes (Rule 4).
  5. TFWS Quota Suffix Compatibility (Rule 5).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class OptionFormBlunder:
    rule_id: str
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "INFO"
    title: str
    description: str
    affected_options: List[int]
    recommended_fix: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "affected_options": self.affected_options,
            "recommended_fix": self.recommended_fix,
        }


@dataclass
class OptionFormAuditReport:
    total_options: int
    risk_score: int  # 0 to 100
    risk_level: str  # "SAFE", "MODERATE_RISK", "CRITICAL_RISK"
    blunders_count: int
    critical_count: int
    high_count: int
    medium_count: int
    blunders: List[OptionFormBlunder] = field(default_factory=list)
    summary_verdict: str = ""
    suggested_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_options": self.total_options,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "blunders_count": self.blunders_count,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "blunders": [b.to_dict() for b in self.blunders],
            "summary_verdict": self.summary_verdict,
            "suggested_actions": self.suggested_actions,
        }


class CAPOptionFormAuditor:
    """Audits drafted option forms against official Maharashtra CAP rules."""

    def __init__(self, cutoff_agent: Optional[Any] = None):
        self.cutoff_agent = cutoff_agent

    def audit_option_form(
        self,
        options: List[Dict[str, Any]],
        student_profile: Dict[str, Any],
    ) -> OptionFormAuditReport:
        """
        Audit student's drafted options against student merit profile.
        options: list of dicts with keys:
          - preference_no (1-indexed int)
          - institute_code (str)
          - institute_name (str, optional)
          - branch (str)
          - cutoff_percentile (float, optional)
          - choice_code (str, optional)
        """
        raw_pct = student_profile.get("percentile") or student_profile.get("score")
        percentile = float(raw_pct) if raw_pct is not None else None
        category = str(student_profile.get("category") or "GOPENS").upper()

        blunders: List[OptionFormBlunder] = []
        n_opts = len(options)

        if n_opts == 0:
            return OptionFormAuditReport(
                total_options=0,
                risk_score=100,
                risk_level="CRITICAL_RISK",
                blunders_count=1,
                critical_count=1,
                high_count=0,
                medium_count=0,
                blunders=[
                    OptionFormBlunder(
                        rule_id="EMPTY_FORM",
                        severity="CRITICAL",
                        title="Empty Option Form",
                        description="You have zero options in your draft. Minimum 1 option is required.",
                        affected_options=[],
                        recommended_fix="Add at least 15 to 30 strategic options across Reach, Target, and Safety tiers."
                    )
                ],
                summary_verdict="Your option form is empty.",
                suggested_actions=["Generate a personalized shortlist using AI-CON."]
            )

        # -------------------------------------------------------------
        # Rule 1: Option #1 Auto-Freeze Risk
        # -------------------------------------------------------------
        opt1 = options[0]
        opt1_cut = opt1.get("cutoff_percentile")
        if percentile is not None and opt1_cut is not None:
            # If Option #1 cutoff is significantly lower than score, it's an auto-freeze risk
            if opt1_cut <= percentile - 1.5:
                inst_name = opt1.get("institute_name") or f"College {opt1.get('institute_code', '')}"
                blunders.append(
                    OptionFormBlunder(
                        rule_id="RULE_1_AUTO_FREEZE_DISASTER",
                        severity="CRITICAL",
                        title="Option #1 Auto-Freeze Risk Detected",
                        description=(
                            f"Option #1 ({inst_name}) has a cutoff of {opt1_cut:.2f}%, which is far below your merit score of {percentile:.2f}%. "
                            f"Under State CET Cell rules, an allotment of Option #1 is COMPULSORY AUTO-FROZEN. "
                            f"You will be permanently locked into this college and completely barred from Betterment in Round 2 and Round 3!"
                        ),
                        affected_options=[1],
                        recommended_fix=(
                            f"Never place a safety college at Option #1. Move your highest dream/aspirational reach college to Option #1."
                        )
                    )
                )

        # -------------------------------------------------------------
        # Rule 2: Inverted Cutoff Order / Preference Inversion
        # -------------------------------------------------------------
        for i in range(len(options)):
            for j in range(i + 1, min(i + 6, len(options))):
                cut_i = options[i].get("cutoff_percentile")
                cut_j = options[j].get("cutoff_percentile")
                if cut_i is not None and cut_j is not None:
                    # Inversion: option i has lower cutoff than option j by more than 1.5%
                    if cut_i < cut_j - 1.5:
                        name_i = options[i].get("institute_name") or f"Option #{i+1}"
                        name_j = options[j].get("institute_name") or f"Option #{j+1}"
                        blunders.append(
                            OptionFormBlunder(
                                rule_id="RULE_2_INVERTED_PREFERENCE",
                                severity="HIGH",
                                title=f"Inverted Preference between #{i+1} and #{j+1}",
                                description=(
                                    f"Option #{i+1} ({name_i}, Cutoff {cut_i:.2f}%) is placed above Option #{j+1} ({name_j}, Cutoff {cut_j:.2f}%). "
                                    f"Because Option #{i+1} has an easier cutoff ({cut_i:.2f}% < {cut_j:.2f}%), the CET Cell algorithm will allot #{i+1} first "
                                    f"and your application will NEVER evaluate the superior college at #{j+1}!"
                                ),
                                affected_options=[i + 1, j + 1],
                                recommended_fix=f"Swap options #{i+1} and #{j+1}: Place the more competitive college #{j+1} above #{i+1}."
                            )
                        )
                        break  # Only flag once per row i to avoid warning explosion

        # -------------------------------------------------------------
        # Rule 3: Missing Safety Net (All-Reach Trap)
        # -------------------------------------------------------------
        if percentile is not None:
            safety_count = sum(
                1 for opt in options
                if opt.get("cutoff_percentile") is not None and opt["cutoff_percentile"] <= percentile - 2.0
            )
            target_count = sum(
                1 for opt in options
                if opt.get("cutoff_percentile") is not None and (percentile - 2.0 < opt["cutoff_percentile"] <= percentile + 0.5)
            )
            reach_count = sum(
                1 for opt in options
                if opt.get("cutoff_percentile") is not None and opt["cutoff_percentile"] > percentile + 0.5
            )

            if safety_count < 2:
                blunders.append(
                    OptionFormBlunder(
                        rule_id="RULE_3_NO_SAFETY_NET",
                        severity="HIGH",
                        title="Dangerous Lack of Safety Options",
                        description=(
                            f"Your list contains {safety_count} safety choices (cutoffs > 2% below your score). "
                            f"You have {reach_count} reach choices and {target_count} target choices. "
                            f"If cutoffs shift upwards even slightly this season, you risk getting ZERO seat allotments in Round 1!"
                        ),
                        affected_options=[idx for idx, _ in enumerate(options, 1)],
                        recommended_fix="Add at least 3 to 5 realistic Safety choices with cutoffs 2.5% to 5.0% below your score."
                    )
                )

        # -------------------------------------------------------------
        # Rule 4: DTE Choice Code Format Validation
        # -------------------------------------------------------------
        for idx, opt in enumerate(options, 1):
            code = opt.get("choice_code")
            if code:
                code_str = str(code).strip()
                is_tfws = code_str.endswith("T")
                core_digits = code_str[:-1] if is_tfws else code_str
                if not core_digits.isdigit() or len(core_digits) != 9:
                    blunders.append(
                        OptionFormBlunder(
                            rule_id="RULE_4_INVALID_CHOICE_CODE",
                            severity="MEDIUM",
                            title=f"Invalid DTE Choice Code at Option #{idx}",
                            description=(
                                f"Option #{idx} specifies choice code '{code_str}', which is not a standard 9-digit CET Cell code. "
                                f"Entering an incorrect choice code on the CET portal may submit you for the wrong branch."
                            ),
                            affected_options=[idx],
                            recommended_fix="Verify the official 9-digit DTE Choice Code from AI-CON verified database."
                        )
                    )

        # -------------------------------------------------------------
        # Rule 5: TFWS Code Consistency
        # -------------------------------------------------------------
        is_user_tfws = "TFWS" in category
        for idx, opt in enumerate(options, 1):
            code = opt.get("choice_code")
            if code and str(code).strip().endswith("T") and not is_user_tfws:
                blunders.append(
                    OptionFormBlunder(
                        rule_id="RULE_5_TFWS_MISMATCH",
                        severity="MEDIUM",
                        title=f"TFWS Code Selected by Non-TFWS Candidate at Option #{idx}",
                        description=(
                            f"Option #{idx} uses TFWS Choice Code '{code}', but your category is stated as '{category}'. "
                            f"Only candidates who opted for TFWS in their CAP application can be allotted 'T' seats."
                        ),
                        affected_options=[idx],
                        recommended_fix=f"Remove the 'T' suffix and use the regular choice code '{str(code).rstrip('T')}'."
                    )
                )

        # Calculate Risk Score (0 to 100)
        crit_c = sum(1 for b in blunders if b.severity == "CRITICAL")
        high_c = sum(1 for b in blunders if b.severity == "HIGH")
        med_c = sum(1 for b in blunders if b.severity == "MEDIUM")

        risk_score = min(100, (crit_c * 40) + (high_c * 20) + (med_c * 10))
        if crit_c > 0 or risk_score >= 60:
            level = "CRITICAL_RISK"
            verdict = "CRITICAL RISK: Do NOT submit this form to the State CET Cell without resolving the flagged blunders."
        elif high_c > 0 or risk_score >= 30:
            level = "MODERATE_RISK"
            verdict = "MODERATE RISK: Several option orders or safety gaps were detected. Review suggested swaps."
        else:
            level = "SAFE"
            verdict = "EXCELLENT & SAFE: Your option form is logically ordered and safe for CET Cell CAP submission."

        actions = [b.recommended_fix for b in blunders if b.severity in ("CRITICAL", "HIGH")]
        if not actions:
            actions = ["Your preference ordering is optimal. You can proceed with form submission."]

        return OptionFormAuditReport(
            total_options=n_opts,
            risk_score=risk_score,
            risk_level=level,
            blunders_count=len(blunders),
            critical_count=crit_c,
            high_count=high_c,
            medium_count=med_c,
            blunders=blunders,
            summary_verdict=verdict,
            suggested_actions=actions,
        )
