"""
AI-CON Structured College Discovery Service (Task 4).
Performs deterministic enumeration across the authoritative college & cutoff datasets:
- Filters by geographic scope (Pune district, Mumbai, etc., with transparent locality aliases).
- Deduplicates by unique institute code (1 college != multiple branch rows).
- Retains all matching branches and cutoff evidence under each institute.
- Diagnostic stats for total master colleges, valid codes, and scope counts.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from scripts.branch_taxonomy import BranchTaxonomyService, BranchResolution
from scripts.agents.cutoff_agent import CutoffAgent

logger = logging.getLogger("aicon.college_discovery")

# Authoritative locality sets for major Maharashtra districts
DISTRICT_LOCALITIES: Dict[str, Set[str]] = {
    "pune": {
        "pune", "alandi", "wagholi", "pimpri", "chinchwad", "tathawade", "bavdhan",
        "hadapsar", "baramati", "lonavala", "maval", "sudumbare", "karvenagar",
        "baner", "balewadi", "vadgaon", "lohgaon", "kothrud", "narhe", "kondhwa",
        "dighi", "bhor", "manchar", "shirur", "someshwar", "talegaon", "akurdi",
        "dhankavdi", "yewalewadi", "lonikand", "warje", "charholi", "lavale"
    },
    "mumbai": {
        "mumbai", "navi mumbai", "bandra", "andheri", "dadar", "chembur", "matunga",
        "sion", "borivali", "vile parle", "thane", "panvel"
    },
    "nagpur": {"nagpur", "ramtek", "kamptee"},
    "nashik": {"nashik", "panchavati", "malegaon", "dindori"},
    "aurangabad": {"aurangabad", "chhatrapati sambhajinagar", "sambhajinagar"},
    "kolhapur": {"kolhapur", "ichalkaranji", "jaysingpur"},
}

# Well-known Pune engineering institutes whose official names in PDFs do not explicitly include "Pune"
PUNE_SPECIAL_CODES: Set[str] = {
    "06006", "6006",  # COEP Technological University
    "06271", "6271",  # Pune Institute of Computer Technology
    "06273", "6273",  # Cummins College of Engineering for Women
    "06274", "6274",  # Pune Vidyarthi Griha's CET
    "06284", "6284",  # Vidya Pratishthan's Kamalnayan Bajaj (Baramati/Pune)
    "06004", "6004",  # Govt College of Engineering & Research, Avasari Khurd
}


@dataclass
class DiscoveredBranchInfo:
    raw_name: str
    canonical_name: str
    canonical_group: str
    latest_cutoff_percentile: Optional[float] = None
    latest_closing_rank: Optional[int] = None
    round_no: Optional[int] = None
    academic_year: Optional[str] = None
    evidence_id: Optional[str] = None
    seat_category: Optional[str] = None


@dataclass
class DiscoveredCollege:
    institute_code: str
    institute_name: str
    city: str
    district: str
    autonomy_type: str
    matching_branches: List[DiscoveredBranchInfo] = field(default_factory=list)
    total_matching_branches: int = 0
    best_cutoff_percentile: Optional[float] = None
    best_closing_rank: Optional[int] = None
    popularity_score: Optional[int] = None
    roi_tier: Optional[str] = None
    evidence_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "institute_code": self.institute_code,
            "institute_name": self.institute_name,
            "city": self.city,
            "district": self.district,
            "autonomy_type": self.autonomy_type,
            "branch": self.matching_branches[0].canonical_name if self.matching_branches else "Engineering",
            "branches": [b.canonical_name for b in self.matching_branches],
            "total_matching_branches": self.total_matching_branches,
            "cutoff_percentile": self.best_cutoff_percentile,
            "closing_rank": self.best_closing_rank,
            "popularity_score": self.popularity_score,
            "roi_tier": self.roi_tier,
            "evidence_id": self.evidence_id,
        }


class StructuredCollegeDiscoveryService:
    """Discovers unique institutes using structured datasets rather than loose top-k vectors."""

    def __init__(self, cutoff_agent: CutoffAgent):
        self.cutoff_agent = cutoff_agent
        self.branch_service = BranchTaxonomyService()
        self._cache_diagnostics()

    def _cache_diagnostics(self):
        """Index total institutes and district boundaries."""
        self.total_institutes = len(self.cutoff_agent._by_code)

    def is_in_location_scope(self, institute_code: str, institute_name: str, location: Optional[str]) -> bool:
        if not location:
            return True
        loc_clean = location.strip().lower()
        target_localities = DISTRICT_LOCALITIES.get(loc_clean, {loc_clean})

        code_str = str(institute_code).zfill(5)
        raw_code = str(institute_code).lstrip("0")
        if loc_clean == "pune" and (code_str in PUNE_SPECIAL_CODES or raw_code in PUNE_SPECIAL_CODES):
            return True

        lower_name = institute_name.lower()
        for loc in target_localities:
            if re.search(r"\b" + re.escape(loc) + r"\b", lower_name):
                return True
        return False

    def discover_colleges(
        self,
        location: Optional[str] = None,
        preferred_branches: Optional[List[str]] = None,
        category: str = "GOPENS",
        percentile: Optional[float] = None,
        rank: Optional[int] = None,
        requested_unique_colleges: int = 30,
        academic_year: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Structured college enumeration returning unique institutes matching location and branch filters.
        Guarantees that 30 colleges means up to 30 unique institutes, not 30 branch rows.
        """
        req_branches = preferred_branches or ["Computer Engineering"]
        cat_upper = category.upper() if category else "GOPENS"
        limit = max(1, requested_unique_colleges)

        discovered_institutes: List[DiscoveredCollege] = []
        seen_codes: Set[str] = set()

        for code, years_map in sorted(self.cutoff_agent._by_code.items()):
            canon_code = code.zfill(5) if len(code) == 4 and code.isdigit() else code
            if canon_code in seen_codes:
                continue

            # Pick latest available year data
            college = None
            if academic_year and academic_year in years_map:
                college = years_map[academic_year]
            else:
                for yr in ["2024-25", "2023-24", "2022-23", "2021-22", "2020-21"]:
                    if yr in years_map:
                        college = years_map[yr]
                        break
            if not college:
                college = list(years_map.values())[-1] if years_map else None
            if not college:
                continue

            inst_name = college.get("institute_name", "")

            # 1. Location scope check
            if not self.is_in_location_scope(canon_code, inst_name, location):
                continue

            # 2. Matching branches check
            matching_branches: List[DiscoveredBranchInfo] = []
            best_pct: Optional[float] = None
            best_rank: Optional[int] = None
            best_ev_id: Optional[str] = None

            for b in college.get("branches", []):
                raw_b_name = b.get("branch", "")
                if not self.branch_service.matches_requested_branch(raw_b_name, req_branches):
                    continue

                b_res = self.branch_service.resolve_branch(raw_b_name)

                # Look up cutoff for this branch & category
                cat_found = None
                for c in b.get("categories", []):
                    if c.get("category", "").upper() == cat_upper:
                        cat_found = c
                        break
                # Fallback to GOPENS if specific quota token absent
                if not cat_found and cat_upper != "GOPENS":
                    for c in b.get("categories", []):
                        if c.get("category", "").upper() == "GOPENS":
                            cat_found = c
                            break

                cut_pct = None
                cut_rank = None
                ev_id = None
                if cat_found:
                    cutoffs = cat_found.get("cutoffs", [])
                    if cutoffs:
                        latest_cut = cutoffs[0]
                        cut_pct = latest_cut.get("closing_percentile")
                        cut_rank = latest_cut.get("closing_rank")
                        ev_id = latest_cut.get("evidence_id")

                # If score filter is active, check attainability
                if percentile is not None and cut_pct is not None:
                    # Include if within reasonable discovery window (percentile +/- 5.0)
                    if cut_pct > percentile + 5.0:
                        continue

                branch_info = DiscoveredBranchInfo(
                    raw_name=raw_b_name,
                    canonical_name=b_res.canonical_name,
                    canonical_group=b_res.canonical_group,
                    latest_cutoff_percentile=cut_pct,
                    latest_closing_rank=cut_rank,
                    round_no=1,
                    academic_year=college.get("academic_year"),
                    evidence_id=ev_id or f"EV-{canon_code}-{cat_upper}-R1",
                    seat_category=cat_upper,
                )
                matching_branches.append(branch_info)

                if cut_pct is not None and (best_pct is None or cut_pct > best_pct):
                    best_pct = cut_pct
                    best_rank = cut_rank
                    best_ev_id = ev_id

            if matching_branches:
                seen_codes.add(canon_code)
                autonomy = "Affiliated"
                if "autonomous" in inst_name.lower():
                    autonomy = "Autonomous"
                elif "government" in inst_name.lower() or "govt" in inst_name.lower():
                    autonomy = "Government"

                discovered_institutes.append(
                    DiscoveredCollege(
                        institute_code=canon_code,
                        institute_name=inst_name,
                        city=location.capitalize() if location else "Maharashtra",
                        district=location.capitalize() if location else "Maharashtra",
                        autonomy_type=autonomy,
                        matching_branches=matching_branches,
                        total_matching_branches=len(matching_branches),
                        best_cutoff_percentile=best_pct,
                        best_closing_rank=best_rank,
                        evidence_id=best_ev_id or f"EV-{canon_code}-{cat_upper}-R1",
                    )
                )

        # Sort by best closing cutoff percentile descending
        discovered_institutes.sort(
            key=lambda c: c.best_cutoff_percentile if c.best_cutoff_percentile is not None else 0.0,
            reverse=True,
        )

        total_matching_unique_institutes = len(discovered_institutes)
        shortlist = discovered_institutes[:limit]

        return {
            "status": "success",
            "requested_unique_colleges": limit,
            "total_matching_unique_institutes": total_matching_unique_institutes,
            "returned_count": len(shortlist),
            "location_scope": location or "Maharashtra",
            "preferred_branches": req_branches,
            "colleges": shortlist,
            "shortfall_explanation": (
                f"Requested {limit} colleges, but only {total_matching_unique_institutes} unique institutes match "
                f"location '{location}' and branch criteria in the authoritative dataset."
                if total_matching_unique_institutes < limit
                else None
            ),
        }

    def get_discovery_diagnostics(self, location: str = "Pune") -> Dict[str, Any]:
        """Diagnostic stats as required by Task 4."""
        total_master = len(self.cutoff_agent._by_code)
        valid_codes = sum(1 for c in self.cutoff_agent._by_code.keys() if c.isdigit() or len(c) >= 4)

        pune_colleges = []
        for code, years in self.cutoff_agent._by_code.items():
            name = list(years.values())[-1].get("institute_name", "")
            if self.is_in_location_scope(code, name, location):
                pune_colleges.append((code, name))

        return {
            "total_master_colleges": total_master,
            "total_valid_codes": valid_codes,
            "total_location_colleges": len(pune_colleges),
            "location": location,
        }

