"""
Deterministic Admission & CAP Rules Engine (AI-con Phase 3.2)
--------------------------------------------------------------
Implements verifiable, deterministic eligibility checking and seat quota resolution
for Maharashtra engineering admissions (MHT-CET CAP counselling).

Strict Separation of Concerns:
1. Student Profile: Captures student examination, domicile, category, and income facts.
2. Official Admission Rules: Versioned criteria by academic cycle.
3. Seat Quota Applicability: Deterministically maps which specific CET quota tokens
   (GOPENH, GOPENO, GOPENS, LOPENH, LOPENO, EWS, TFWS, AI, etc.) a student is eligible for.
4. Explanations: Always provides transparent legal and procedural justifications.
   Never guesses missing facts; explicitly flags what is required to resolve eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


TFWS_INCOME_LIMIT_INR = 800000.0  # 8 Lakhs per annum statutory limit


@dataclass
class StudentProfile:
    """Represents a student candidate profile for admission counselling."""

    academic_year: str = "2025-26"
    entrance_exam: str = "MHT-CET"  # "MHT-CET" or "JEE-Main"
    percentile: Optional[float] = None
    merit_rank: Optional[int] = None
    caste_category: str = "OPEN"  # OPEN, OBC, SC, ST, VJ/DT, NT1, NT2, NT3, SBC, SEBC, EWS
    domicile: str = "Maharashtra"  # "Maharashtra" or "OMS" (Outside Maharashtra State)
    home_university: Optional[str] = None  # e.g., "Amravati", "Pune", "Mumbai"
    gender: Optional[str] = "Male"  # "Male", "Female", "Other"
    annual_income: Optional[float] = None  # in INR
    has_caste_validity: Optional[bool] = None
    has_non_creamy_layer: Optional[bool] = None  # Required for OBC, SBC, VJ, NT, SEBC
    has_ews_certificate: Optional[bool] = None  # Required for EWS
    tfws_opted: Optional[bool] = None  # Tuition Fee Waiver Scheme
    defense_type: Optional[str] = None  # DEF1, DEF2, DEF3
    pwd_status: Optional[bool] = False
    orphan_status: Optional[bool] = False

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class EligibilityResult:
    """Detailed evaluation result returned by the AdmissionRulesEngine."""

    status: str  # "eligible", "ineligible", "needs_verification"
    candidature_type: str  # "Maharashtra State (Type A/B)", "All India (OMS)", etc.
    applicable_categories: List[str]  # Tokens the student can legally claim in CAP
    explanations: List[str]
    missing_fields: List[str] = field(default_factory=list)
    rule_version: str = "2025-26"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "candidature_type": self.candidature_type,
            "applicable_categories": self.applicable_categories,
            "explanations": self.explanations,
            "missing_fields": self.missing_fields,
            "rule_version": self.rule_version,
        }


class AdmissionRulesEngine:
    """Evaluates student eligibility and resolves applicable seat quota categories."""

    def __init__(self, rule_year: str = "2025-26"):
        self.rule_year = rule_year

    def evaluate_student(
        self,
        student: StudentProfile,
        target_college_university: Optional[str] = None,
        is_autonomous_or_state_level: bool = False,
    ) -> EligibilityResult:
        """Determines eligibility, candidature type, and all applicable quota categories."""
        explanations: List[str] = []
        missing_fields: List[str] = []
        applicable_categories: Set[str] = set()

        # 1. Entrance Score Evaluation
        if student.percentile is None and student.merit_rank is None:
            missing_fields.append("percentile_or_merit_rank")
            explanations.append(
                "Neither entrance percentile nor merit rank was supplied. "
                "A non-zero score is required for CAP merit allocation."
            )

        # 2. Domicile & Candidature Type
        domicile_clean = (student.domicile or "").strip().lower()
        is_oms = domicile_clean in ("oms", "outside maharashtra", "non-maharashtra")

        if is_oms:
            candidature_type = "All India Candidature (OMS)"
            explanations.append(
                "Candidate is classified as Outside Maharashtra State (OMS). "
                "Eligible for All India seats (AI) via JEE Main (or MHT-CET if AI seats remain vacant)."
            )
            applicable_categories.add("AI")
            status = "needs_verification" if missing_fields else "eligible"
            return EligibilityResult(
                status=status,
                candidature_type=candidature_type,
                applicable_categories=sorted(applicable_categories),
                explanations=explanations,
                missing_fields=missing_fields,
                rule_version=self.rule_year,
            )

        candidature_type = "Maharashtra State Candidature (Type A)"
        explanations.append("Candidate is classified under Maharashtra State Candidature.")

        # In Maharashtra State, All India (AI) seats are also open if candidate has valid score
        applicable_categories.add("AI")

        # 3. Quota Scope: Home University (HU) vs Other than Home University (OHU) vs State Level (SL)
        is_female = (student.gender or "").strip().lower() in ("female", "f")
        same_university = False

        if target_college_university and student.home_university:
            s_u = student.home_university.strip().lower()
            c_u = target_college_university.strip().lower()
            same_university = (s_u in c_u) or (c_u in s_u)
        elif not is_autonomous_or_state_level and not student.home_university:
            missing_fields.append("home_university")
            explanations.append(
                "Candidate home_university is unspecified. "
                "Cannot distinguish Home University (HU) from Other Than Home University (OHU) quotas."
            )

        # General Open Quotas
        if is_autonomous_or_state_level:
            applicable_categories.add("GOPENS")
            if is_female:
                applicable_categories.add("LOPENS")
            explanations.append("Institution operates under State Level quota (SL): GOPENS applies.")
        else:
            if student.home_university:
                if same_university:
                    applicable_categories.add("GOPENH")
                    if is_female:
                        applicable_categories.add("LOPENH")
                    explanations.append("Candidate home university matches college university: GOPENH applies.")
                else:
                    applicable_categories.add("GOPENO")
                    if is_female:
                        applicable_categories.add("LOPENO")
                    explanations.append("College university differs from candidate home university: GOPENO applies.")
            else:
                explanations.append(
                    "Candidate home university is unspecified; cannot resolve Home University (HU) vs "
                    "Other than Home University (OHU) quota. Only State Level (GOPENS) is evaluated."
                )
            # State level open seats always available in CAP
            applicable_categories.add("GOPENS")
            if is_female:
                applicable_categories.add("LOPENS")

        # 4. Reserved Category Evaluation
        cat = (student.caste_category or "OPEN").strip().upper()
        requires_ncl = cat in ("OBC", "SBC", "VJ/DT", "NT1", "NT2", "NT3", "SEBC")

        if cat != "OPEN":
            # Caste Validity Check
            if student.has_caste_validity is False:
                explanations.append(
                    f"Candidate lacks Caste Validity Certificate. By official rule, "
                    f"{cat} reservation cannot be claimed; seat allocation falls back to OPEN."
                )
            elif student.has_caste_validity is None:
                missing_fields.append("has_caste_validity")
                explanations.append(
                    f"Caste Validity Certificate verification is pending for {cat} candidate."
                )

            # Non-Creamy Layer Check
            if requires_ncl:
                if student.has_non_creamy_layer is False:
                    explanations.append(
                        f"Non-Creamy Layer Certificate is missing. Candidate cannot claim {cat} quota; "
                        f"falls back to OPEN."
                    )
                elif student.has_non_creamy_layer is None:
                    missing_fields.append("has_non_creamy_layer")
                    explanations.append(
                        f"Non-Creamy Layer verification is pending for {cat} candidate."
                    )

            # If not disqualified, add category quota tokens
            if student.has_caste_validity is not False and (not requires_ncl or student.has_non_creamy_layer is not False):
                cat_core = cat.replace("/", "")
                if is_autonomous_or_state_level:
                    applicable_categories.add(f"G{cat_core}S")
                    if is_female:
                        applicable_categories.add(f"L{cat_core}S")
                else:
                    if student.home_university:
                        scope = "H" if same_university else "O"
                        applicable_categories.add(f"G{cat_core}{scope}")
                        if is_female:
                            applicable_categories.add(f"L{cat_core}{scope}")
                    applicable_categories.add(f"G{cat_core}S")
                    if is_female:
                        applicable_categories.add(f"L{cat_core}S")
                explanations.append(f"Candidate qualifies for {cat} reserved quota seats (subject to certificate verification).")

        # 5. EWS (Economically Weaker Section) Evaluation
        if cat == "EWS" or student.has_ews_certificate is True:
            if student.has_ews_certificate is False:
                explanations.append("EWS Certificate is missing; cannot claim EWS 10% supernumerary quota.")
            else:
                applicable_categories.add("EWS")
                explanations.append("Candidate qualifies for EWS (10% state-level supernumerary quota).")
        elif student.has_ews_certificate is None and cat == "EWS":
            missing_fields.append("has_ews_certificate")

        # 6. TFWS (Tuition Fee Waiver Scheme) Evaluation
        if student.tfws_opted is True:
            if student.annual_income is not None:
                if student.annual_income <= TFWS_INCOME_LIMIT_INR:
                    applicable_categories.add("TFWS")
                    explanations.append(
                        f"Annual family income (Rs. {student.annual_income:,.0f}) is within statutory limit "
                        f"(<= Rs. 8,00,000). Eligible for TFWS 5% supernumerary quota."
                    )
                else:
                    explanations.append(
                        f"Annual family income (Rs. {student.annual_income:,.0f}) exceeds Rs. 8,00,000 limit. "
                        f"Ineligible for TFWS."
                    )
            else:
                missing_fields.append("annual_income")
                explanations.append("Annual family income must be verified for TFWS eligibility.")

        # 7. Defense & PWD Special Quotas
        if student.defense_type:
            def_token = student.defense_type.strip().upper()
            applicable_categories.add(def_token)
            explanations.append(f"Candidate qualifies for Defense personnel quota ({def_token}).")

        if student.pwd_status:
            applicable_categories.add("PWDOPEN")
            explanations.append("Candidate qualifies for Persons with Disability (PWD) reservation.")

        status = "needs_verification" if missing_fields else "eligible"

        return EligibilityResult(
            status=status,
            candidature_type=candidature_type,
            applicable_categories=sorted(applicable_categories),
            explanations=explanations,
            missing_fields=missing_fields,
            rule_version=self.rule_year,
        )
