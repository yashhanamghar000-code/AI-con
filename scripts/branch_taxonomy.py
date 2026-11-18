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

