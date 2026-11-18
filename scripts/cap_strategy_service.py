"""
AI-CON CAP Strategy & Option Form Intelligence Service (Phase 1 & Phase 2).
Provides:
1. Option Form Balance & Risk Evaluation (Reach, Competitive, Attainable balance)
2. Inverted Preference Ordering Detection
3. Official DTE Choice List CSV Export
4. Round 1 / Round 2 "Freeze vs Float" Decision Simulator
5. Mandatory Document Verification Checklist Generator
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional


class CAPStrategyService:
    """
    Statutory admission intelligence for Maharashtra CAP Engineering admissions.
    Adheres strictly to DTE Maharashtra / State CET Cell allocation rules.
    """

    @staticmethod
    def validate_option_form(
        choices: List[Dict[str, Any]],
        student_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Validates the candidate's option preference list for risk, tier distribution,
        and common strategic errors under CAP allocation rules.
        """
        if not choices:
            return {
                "valid": False,
                "risk_level": "empty",
                "is_balanced": False,
                "total_choices": 0,
                "message": "Option form is empty. Add at least 5-10 colleges across Reach, Competitive, and Attainable tiers.",
                "tier_breakdown": {"reach": 0, "competitive": 0, "attainable": 0, "other": 0},
                "recommendations": ["Search colleges in your preferred districts and click '+ Add to Option Form'."],
            }

        total = len(choices)
        reach_count = 0
        comp_count = 0
        attainable_count = 0
        other_count = 0

        for c in choices:
            tier = str(c.get("tier") or c.get("feasibility_tier") or "").lower()
            if "reach" in tier:
                reach_count += 1
            elif "competitive" in tier:
                comp_count += 1
            elif "attainable" in tier or "safe" in tier:
                attainable_count += 1
            else:
                other_count += 1

        reach_pct = round((reach_count / total) * 100, 1)
        comp_pct = round((comp_count / total) * 100, 1)
        attainable_pct = round((attainable_count / total) * 100, 1)

        recommendations: List[str] = []
        risk_level = "balanced"

        # Check total option count
        if total < 5:
            risk_level = "high_risk"
            recommendations.append(f"You have only selected {total} option(s). CET Cell allows up to 300 choice codes. We recommend at least 15-20 options to avoid being unallotted.")
        elif total < 10:
            recommendations.append("Consider adding 5-10 more backup choices to maximize your admission chances across rounds.")

        # Safety / Attainable check
        if attainable_count == 0:
            risk_level = "high_risk"
            recommendations.append("⚠️ Critical Risk: No 'Historically More Attainable' colleges in your list! If cutoffs rise this year, you risk zero allotments in CAP Round 1.")
        elif attainable_pct < 20.0:
            if risk_level != "high_risk":
                risk_level = "moderate_risk"
            recommendations.append("Attainable backup options make up less than 20% of your list. Add 3-5 more colleges where your score comfortably clears past cutoffs.")

        # Top-heavy check
        if reach_pct > 65.0:
            if risk_level != "high_risk":
                risk_level = "moderate_risk"
            recommendations.append("Your list is top-heavy with over 65% Reach choices. Balance it with more Competitive and Attainable programs.")

        # Check Inverted Order (e.g. putting a lower cutoff choice ahead of a higher cutoff choice in the same branch)
        inversion_warnings = []
        for i in range(len(choices) - 1):
            curr = choices[i]
            nxt = choices[i + 1]
            curr_co = curr.get("cutoff_percentile")
            nxt_co = nxt.get("cutoff_percentile")
            if curr_co is not None and nxt_co is not None:
                if (curr_co < nxt_co - 2.0) and (curr.get("branch") == nxt.get("branch")):
                    inversion_warnings.append(
                        f"Choice #{i+1} ({curr.get('institute_name')}, Cutoff: {curr_co}%) has a significantly lower cutoff than Choice #{i+2} ({nxt.get('institute_name')}, Cutoff: {nxt_co}%). If you prefer Choice #{i+2}, place it higher in your list."
                    )

        if inversion_warnings:
            recommendations.extend(inversion_warnings[:2])

        # Statutory Auto-freeze Notice for Choice 1
        statutory_notes = [
            "Rule 9(1): If your Choice #1 is allotted in Round 1, the seat is AUTOMATICALLY FROZEN. You must pay the acceptance fee and take admission; you cannot participate in Round 2.",
            "Rule 9(2): For Choice #2 and below, you can choose 'Betterment (Float)' to keep your allotted seat while trying for higher preferences in Round 2.",
        ]

        is_balanced = (risk_level == "balanced")
        return {
            "valid": True,
            "total_choices": total,
            "risk_level": risk_level,
            "is_balanced": is_balanced,
            "tier_breakdown": {
                "reach_count": reach_count,
                "reach_pct": reach_pct,
                "competitive_count": comp_count,
                "competitive_pct": comp_pct,
                "attainable_count": attainable_count,
                "attainable_pct": attainable_pct,
                "other_count": other_count,
            },
            "recommendations": recommendations,
            "statutory_notes": statutory_notes,
        }

    @staticmethod
    def export_dte_csv(choices: List[Dict[str, Any]]) -> str:
        """
        Exports the candidate's option list in a format compliant with the DTE Maharashtra CAP portal.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Preference_Number",
            "Choice_Code",
            "Institute_Code",
            "Institute_Name",
            "Course_Branch_Name",
            "Category",
            "Historical_Cutoff_Percentile",
            "Feasibility_Tier"
        ])

        for idx, item in enumerate(choices, start=1):
            choice_code = item.get("choice_code") or f"{item.get('institute_code', '0000')}24510"
            inst_code = item.get("institute_code") or ""
            inst_name = item.get("institute_name") or ""
            branch = item.get("branch") or item.get("branch_name") or ""
            cat = item.get("category") or "GOPENS"
            co = item.get("cutoff_percentile") or "N/A"
            tier = item.get("tier") or item.get("feasibility_tier") or "Competitive"

            writer.writerow([
                idx,
                choice_code,
                inst_code,
                inst_name,
                branch,
                cat,
                co,
                tier
            ])

        return output.getvalue()

    @staticmethod
    def analyze_freeze_float(
        allotted_choice_no: int,
        allotted_choice_code: str,
        allotted_institute_name: str,
        cap_round: int,
        student_percentile: float,
        category: str = "GOPENS",
        higher_choices: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Analyzes whether a student should Freeze or Float/Betterment based on statutory CAP rules
        and historical Round-to-Round cutoff shifts.
        """
        higher_choices = higher_choices or []

        # Case 1: First Choice Allotment
        if allotted_choice_no == 1:
            return {
                "decision": "AUTO_FREEZE",
                "headline": "Mandatory Auto-Freeze (Statutory Rule)",
                "action_required": "Accept Seat & Confirm Admission",
                "explanation": (
                    f"Congratulations! You were allotted your first preference: Choice #1 ({allotted_institute_name}). "
                    "Under Maharashtra State CET Cell Rule 9(a), Choice #1 is automatically frozen. "
                    "You CANNOT participate in subsequent CAP rounds. You must pay the Seat Acceptance Fee and confirm your admission at the allotted institute."
                ),
                "steps": [
                    "1. Log in to the official State CET Cell CAP portal.",
                    "2. Verify candidate details and complete online seat acceptance.",
                    "3. Pay the Seat Acceptance Fee (Rs. 1,000) online.",
                    "4. Report to the allotted institute with original documents within the scheduled window.",
                ],
                "risk_of_losing_seat": "Zero (Seat is confirmed once fee is paid)",
            }

        # Case 2: Final CAP Round (Round 3)
        if cap_round >= 3:
            return {
                "decision": "FINAL_ROUND_FREEZE",
                "headline": "Confirm Seat (Final CAP Round)",
                "action_required": "Self-Freeze & Report to Institute",
                "explanation": (
                    f"You have been allotted Choice #{allotted_choice_no} ({allotted_institute_name}) in Round {cap_round}. "
                    "Since this is the final centralized CAP round, no further centralized betterments exist. "
                    "Freeze this seat to secure your admission, or participate only in institutional non-CAP spot rounds at your own risk."
                ),
                "steps": [
                    "1. Select 'Self-Freeze' on the CET portal.",
                    "2. Pay the Seat Acceptance Fee if not paid in earlier rounds.",
                    "3. Complete physical reporting and fee payment at the college.",
                ],
                "risk_of_losing_seat": "Low if frozen before reporting deadline.",
            }

        # Case 3: Choices #2 and below in Round 1 or Round 2 -> Float / Betterment Option
        viable_betterments: List[Dict[str, Any]] = []
        for hc in higher_choices:
            cutoff = hc.get("cutoff_percentile")
            if cutoff is not None:
                margin = cutoff - student_percentile
                # In Round 2/3, cutoffs often drop by 0.5% to 2.5%
                if margin <= 2.5:
                    viable_betterments.append({
                        "choice_no": hc.get("preference_no"),
                        "institute_name": hc.get("institute_name"),
                        "branch": hc.get("branch"),
                        "cutoff_percentile": cutoff,
                        "gap": round(margin, 2),
                        "chance": "High" if margin <= 0.8 else ("Moderate" if margin <= 1.8 else "Possible"),
                    })

        if viable_betterments:
            decision = "FLOAT_FOR_BETTERMENT"
            headline = "Recommend: Betterment (Float) for Next Round"
            explanation = (
                f"You were allotted Choice #{allotted_choice_no} ({allotted_institute_name}). "
                f"You have {len(viable_betterments)} higher choice(s) where historical cutoffs are within reachable range (≤ 2.5% margin). "
                "Choosing 'Betterment' guarantees that your currently allotted seat remains 100% reserved for you as a safety backup. "
                "If you get a higher choice in Round 2, you upgrade; if not, you keep your current seat."
            )
        else:
            decision = "CONSIDER_SELF_FREEZE"
            headline = "Consider Self-Freeze or Selective Betterment"
            explanation = (
                f"You were allotted Choice #{allotted_choice_no} ({allotted_institute_name}). "
                "Your higher preferences had cutoffs significantly above your current score (> 2.5% higher). "
                "While choosing Betterment carries NO risk of losing your current seat, your chances of upgrading to higher options in Round 2 are limited. "
                "If you are happy with this institute, you may Self-Freeze and confirm admission."
            )

        return {
            "decision": decision,
            "headline": headline,
            "action_required": "Choose 'Betterment' or 'Self-Freeze' on CET Portal",
            "explanation": explanation,
            "allotted_choice": f"Choice #{allotted_choice_no}: {allotted_institute_name}",
            "viable_betterment_options": viable_betterments,
            "key_safety_guarantee": "Under statutory DTE rules, selecting 'Betterment' NEVER loses your currently allotted seat until a higher choice is alloted in Round 2.",
            "steps": [
                "1. Pay the Seat Acceptance Fee (Rs. 1,000) online — this is MANDATORY to retain your seat.",
                "2. In the allotment status option, choose 'Betterment (Not Freeze)'.",
                "3. In Round 2, you may optionally edit or reorder higher preference choices.",
            ],
        }

    @staticmethod
    def get_document_checklist(
        category: str = "OPEN",
        has_tfws: bool = False,
        has_ews: bool = False,
        has_pwd: bool = False,
        has_def: bool = False,
        annual_income: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Generates the official Maharashtra DTE Scrutiny Center document checklist.
        """
        cat_upper = category.upper()

        common_docs = [
            {
                "title": "SSC (Std. X) Marksheet & Passing Certificate",
                "issuing_authority": "State Board / CBSE / ICSE",
                "purpose": "Proof of Date of Birth and aggregate qualification",
                "is_mandatory": True,
            },
            {
                "title": "HSC (Std. XII) Marksheet & Passing Certificate",
                "issuing_authority": "State Board / CBSE / ICSE",
                "purpose": "Physics + Mathematics + Chem/CS eligibility marks check",
                "is_mandatory": True,
            },
            {
                "title": "MHT-CET / JEE Main Score Card",
                "issuing_authority": "State CET Cell Maharashtra / NTA",
                "purpose": "Official percentile and State General Merit Number proof",
                "is_mandatory": True,
            },
            {
                "title": "Maharashtra State Domicile Certificate / Birth Certificate",
                "issuing_authority": "Executive Magistrate / Tehsildar",
                "purpose": "Proof of Maharashtra Candidature (Type A/B/C/D)",
                "is_mandatory": True,
            },
            {
                "title": "School / College Leaving Certificate (LC / TC)",
                "issuing_authority": "Junior College / School Principal",
                "purpose": "Proof of nationality, mother tongue, and domicile",
                "is_mandatory": True,
            },
        ]

        category_docs = []

        # Reserved Categories (OBC, SC, ST, VJ/NT, SBC)
        if cat_upper in ("GOBCS", "OBC", "GSCS", "SC", "GSTS", "ST", "GVJS", "VJ", "GNT1S", "NT1", "GNT2S", "NT2", "GNT3S", "NT3", "SBC"):
            category_docs.append({
                "title": f"Caste Certificate ({cat_upper})",
                "issuing_authority": "Sub-Divisional Officer (SDO) / Deputy Collector",
                "purpose": "Proof of backward class category reservation",
                "is_mandatory": True,
            })
            category_docs.append({
                "title": "Caste Validity Certificate (CVC)",
                "issuing_authority": "Divisional Caste Scrutiny Committee",
                "purpose": "CRITICAL: Without CVC, seat is converted to OPEN category under statutory rules.",
                "is_mandatory": True,
                "warning": "Receipt of application is permitted only if accompanied by prescribed Undertaking Form Proforma-H.",
            })

            # Non-Creamy Layer for OBC, VJ/NT, SBC
            if cat_upper not in ("GSCS", "SC", "GSTS", "ST"):
                category_docs.append({
                    "title": "Non-Creamy Layer Certificate (NCL)",
                    "issuing_authority": "Sub-Divisional Officer / Tehsildar",
                    "purpose": "MANDATORY: Must be valid up to 31st March 2027.",
                    "is_mandatory": True,
                    "warning": "Expired NCL certificates are strictly rejected by the Scrutiny Center.",
                })

        # EWS
        if has_ews or cat_upper == "EWS":
            category_docs.append({
                "title": "EWS Eligibility Certificate",
                "issuing_authority": "Tehsildar / Competent Revenue Authority",
                "purpose": "Economically Weaker Section (10% state reservation quota)",
                "is_mandatory": True,
                "validity": "Valid for the current financial year (family income < Rs. 8 Lakh)",
            })

        # TFWS (Tuition Fee Waiver Scheme)
        if has_tfws or (annual_income is not None and annual_income <= 800000):
            category_docs.append({
                "title": "Income Certificate for FY 2025-26",
                "issuing_authority": "Tehsildar",
                "purpose": "MANDATORY for TFWS / EBC Fee Concession (Family income must be <= Rs. 8 Lakh)",
                "is_mandatory": True,
            })

        # PwD (Persons with Disability)
        if has_pwd:
            category_docs.append({
                "title": "Unique Disability ID (UDID) Card / Disability Certificate",
                "issuing_authority": "District Medical Board / Competent Medical Authority",
                "purpose": "Minimum 40% benchmark disability proof for PwD reservation",
                "is_mandatory": True,
            })

        # Defense Personnel
        if has_def:
            category_docs.append({
                "title": "Defense Service Certificate (Proforma C / D / E)",
                "issuing_authority": "Zilla Sainik Board / Commanding Officer",
                "purpose": "Proof of defense category candidature (Def-1 / Def-2 / Def-3)",
                "is_mandatory": True,
            })

        return {
            "category": cat_upper,
            "total_documents": len(common_docs) + len(category_docs),
            "common_documents": common_docs,
            "category_specific_documents": category_docs,
            "scrutiny_guidelines": [
                "Original documents MUST be produced for physical e-Scrutiny / physical reporting.",
                "Ensure candidate name matches EXACTLY across SSC marksheet, HSC marksheet, and Caste Certificate.",
                "Keep at least 4 attested photocopies and high-resolution scanned PDFs of every document.",
            ],
        }
