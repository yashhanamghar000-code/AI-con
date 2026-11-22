"""
AI-CON Branch Taxonomy and Canonical Entity Resolution Module (Task 5).
Maps raw, scraped, and truncated branch strings to official canonical disciplines,
canonical branch groups, and standard normalized codes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class BranchResolution:
    raw_name: str
    canonical_name: str
    canonical_group: str
    match_confidence: float
    match_reason: str
    is_truncated_repaired: bool = False


# Canonical branch group hierarchy
BRANCH_GROUPS = {
    "Computer Engineering": "Computer & IT Engineering",
    "Computer Science and Engineering": "Computer & IT Engineering",
    "Information Technology": "Computer & IT Engineering",
    "Artificial Intelligence and Data Science": "AI, Data Science & Machine Learning",
    "Computer Science and Engineering(Artificial Intelligence and Machine Learning)": "AI, Data Science & Machine Learning",
    "Computer Science and Engineering (Data Science)": "AI, Data Science & Machine Learning",
    "Computer Engineering (Software Engineering)": "Computer & IT Engineering",
    "Electronics and Computer Engineering": "Specialized / Multidisciplinary",
    "Mechanical Engineering": "Mechanical Engineering",
    "Civil Engineering": "Civil Engineering",
    "Electrical Engineering": "Electrical Engineering",
    "Electronics and Telecommunication Engg": "Electronics & Telecommunication",
    "Chemical Engineering": "Chemical Engineering",
    "Aerospace Engineering": "Aerospace & Aeronautical",
}

# Explicit repairs for truncated legacy header names observed in CET Cell PDFs
KNOWN_TRUNCATION_REPAIRS: Dict[str, str] = {
    "computer science and engineering(artificial": "Computer Science and Engineering(Artificial Intelligence and Machine Learning)",
    "computer science and engineering(artificial intelligence": "Computer Science and Engineering(Artificial Intelligence and Machine Learning)",
    "computer science and engineering (artificial intelligence": "Computer Science and Engineering(Artificial Intelligence and Machine Learning)",
    "artificial intelligence (ai) (degree), wadwadi and data science": "Artificial Intelligence and Data Science",
    "artificial intelligence and (bk.), pune data science": "Artificial Intelligence and Data Science",
    "artificial intelligence and": "Artificial Intelligence and Data Science",
    "electronics and telecommunication": "Electronics and Telecommunication Engg",
    "electronics and communication engineering": "Electronics and Telecommunication Engg",
    "computer technology": "Computer Technology",
    "computer science and design": "Computer Science and Design",
}


class BranchTaxonomyService:
    """Provides canonical resolution and categorization for engineering disciplines."""

    def __init__(self):
        self._canonical_names: List[str] = list(BRANCH_GROUPS.keys())

    def resolve_branch(self, raw_branch: str) -> BranchResolution:
        if not raw_branch or not raw_branch.strip():
            return BranchResolution(
                raw_name="",
                canonical_name="General Engineering",
                canonical_group="General",
                match_confidence=0.0,
                match_reason="empty_query",
            )

        clean = raw_branch.strip()
        lower = clean.lower()

        # 1. Exact Truncation / Known Repair Match
        for trunc_pat, repaired in KNOWN_TRUNCATION_REPAIRS.items():
            if lower == trunc_pat or lower.startswith(trunc_pat):
                return BranchResolution(
                    raw_name=clean,
                    canonical_name=repaired,
                    canonical_group=BRANCH_GROUPS.get(repaired, "Computer & IT Engineering"),
                    match_confidence=0.98,
                    match_reason=f"repaired_truncation_from_{trunc_pat}",
                    is_truncated_repaired=True,
                )

        # 2. Strict Exact Canonical Match
        for cname in self._canonical_names:
            if lower == cname.lower():
                return BranchResolution(
                    raw_name=clean,
                    canonical_name=cname,
                    canonical_group=BRANCH_GROUPS.get(cname, "Other"),
                    match_confidence=1.0,
                    match_reason="exact_canonical_match",
                )

        # 3. Electronics and Computer Engineering (DO NOT conflate with pure Computer Engineering!)
        if "electronics" in lower and "computer" in lower:
            cname = "Electronics and Computer Engineering"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.95,
                match_reason="multidisciplinary_electronics_computer",
            )

        # 4. Software Engineering sub-discipline
        if "software engineering" in lower:
            cname = "Computer Engineering (Software Engineering)"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.95,
                match_reason="software_engineering_specialization",
            )

        # 5. AI & ML variants
        if any(pat in lower for pat in ["machine learning", "aiml", "ai and ml", "ai & ml"]):
            cname = "Computer Science and Engineering(Artificial Intelligence and Machine Learning)"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.92,
                match_reason="ai_ml_specialization",
            )

        # 6. Data Science variants
        if any(pat in lower for pat in ["data science", "aids", "ai & ds", "ai and ds", "data analytics"]):
            if "artificial" in lower or "ai" in lower:
                cname = "Artificial Intelligence and Data Science"
            else:
                cname = "Computer Science and Engineering (Data Science)"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.92,
                match_reason="data_science_specialization",
            )

        # 7. Information Technology
        if "information technology" in lower or lower in ("it", "infotech"):
            cname = "Information Technology"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.95,
                match_reason="information_technology_standard",
            )

        # 8. Computer Science & Engineering vs Computer Engineering
        if "computer science and engineering" in lower or "cse" in lower:
            cname = "Computer Science and Engineering"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.90,
                match_reason="computer_science_engineering",
            )

        if "computer" in lower or "comp" in lower:
            cname = "Computer Engineering"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.90,
                match_reason="computer_engineering_canonical",
            )

        # 9. Other Standard Branches
        if "mechanical" in lower:
            cname = "Mechanical Engineering"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.95,
                match_reason="mechanical_engineering",
            )
        if "civil" in lower:
            cname = "Civil Engineering"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.95,
                match_reason="civil_engineering",
            )
        if "electrical" in lower:
            cname = "Electrical Engineering"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.95,
                match_reason="electrical_engineering",
            )
        if any(k in lower for k in ["telecommunication", "entc", "communication"]):
            cname = "Electronics and Telecommunication Engg"
            return BranchResolution(
                raw_name=clean,
                canonical_name=cname,
                canonical_group=BRANCH_GROUPS[cname],
                match_confidence=0.90,
                match_reason="entc_engineering",
            )

        return BranchResolution(
            raw_name=clean,
            canonical_name=clean,
            canonical_group="Other Engineering",
            match_confidence=0.50,
            match_reason="raw_preserved_fallback",
        )

    def matches_requested_branch(self, college_branch: str, requested_branches: List[str]) -> bool:
        """Determines if a college branch satisfies any of the requested branch criteria."""
        if not requested_branches:
            return True
        res = self.resolve_branch(college_branch)
        for req in requested_branches:
            req_res = self.resolve_branch(req)
            # Exact canonical equality
            if res.canonical_name.lower() == req_res.canonical_name.lower():
                return True
            # Same group if related branches was requested
            if req.lower() in ("related", "computer", "all related") and res.canonical_group == "Computer & IT Engineering":
                return True
            # Substring stem check
            if req.lower() in college_branch.lower():
                return True
        return False


# Official Maharashtra State Common Entrance Test Cell (CET Cell) Course Suffixes
CANONICAL_DTE_COURSE_CODES: Dict[str, str] = {
    "Computer Engineering": "245",
    "Computer Science and Engineering": "242",
    "Information Technology": "242",
    "Artificial Intelligence and Data Science": "246",
    "Computer Science and Engineering(Artificial Intelligence and Machine Learning)": "911",
    "Computer Science and Engineering (Data Science)": "251",
    "Computer Science and Design": "262",
    "Computer Technology": "245",
    "Electronics and Computer Engineering": "897",
    "Electronics and Telecommunication Engg": "372",
    "Electrical Engineering": "293",
    "Mechanical Engineering": "612",
    "Civil Engineering": "191",
    "Chemical Engineering": "507",
    "Aerospace Engineering": "002",
}


def format_dte_choice_code(
    raw_course_code: Optional[str] = None,
    institute_code: str = "",
    branch_name: str = "",
    category: str = "GOPENS",
    shift: str = "10"
) -> str:
    """
    Format authoritative 9-digit Maharashtra State CET Cell DTE Choice Code.
    Structure: [4-digit Institute Code] + [3-digit Course Code] + [2-digit Shift/Status, e.g. 10]
    For TFWS: appends 'T' (e.g. 617524510T)
    """
    is_tfws = "TFWS" in (category or "").upper()

    # 1. If raw course code is already provided from official CET dataset:
    if raw_course_code and str(raw_course_code).strip():
        clean_code = str(raw_course_code).strip().upper()
        if clean_code.endswith("T"):
            clean_code = clean_code[:-1]

        # If it is a 10-digit number starting with 0 (e.g. 0617524510), strip leading zero
        if len(clean_code) == 10 and clean_code.startswith("0") and clean_code[1:].isdigit():
            clean_code = clean_code[1:]

        # If it is a valid 9-digit numeric string
        if len(clean_code) == 9 and clean_code.isdigit():
            return f"{clean_code}T" if is_tfws else clean_code

    # 2. Synthesize deterministically from institute code and branch
    clean_inst = str(institute_code).strip().lstrip("0")
    if len(clean_inst) < 4:
        clean_inst = clean_inst.zfill(4)
    elif len(clean_inst) > 4:
        clean_inst = clean_inst[-4:]

    # Resolve course suffix
    course_suffix = "245"  # default Computer
    if branch_name:
        for cname, code in CANONICAL_DTE_COURSE_CODES.items():
            if cname.lower() in branch_name.lower():
                course_suffix = code
                break
        else:
            lower_b = branch_name.lower()
            if "information" in lower_b or "it" in lower_b:
                course_suffix = "242"
            elif "data" in lower_b or "ai" in lower_b:
                course_suffix = "246"
            elif "civil" in lower_b:
                course_suffix = "191"
            elif "mech" in lower_b:
                course_suffix = "612"
            elif "elect" in lower_b:
                course_suffix = "293"
            elif "entc" in lower_b or "telecom" in lower_b:
                course_suffix = "372"

    shift_suffix = shift if len(shift) == 2 else "10"
    base_9_digit = f"{clean_inst}{course_suffix}{shift_suffix}"
    return f"{base_9_digit}T" if is_tfws else base_9_digit

