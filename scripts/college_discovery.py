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

try:
    from scripts.branch_taxonomy import BranchTaxonomyService, BranchResolution, format_dte_choice_code
except ImportError:
    from branch_taxonomy import BranchTaxonomyService, BranchResolution, format_dte_choice_code
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
    choice_code: Optional[str] = None
    course_code: Optional[str] = None


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
    popularity_score: Optional[float] = None
    popularity_available: bool = False
    roi_tier: Optional[str] = None
    evidence_id: Optional[str] = None
    choice_code: Optional[str] = None
    fee_data: Optional[Dict[str, Any]] = None
    placement_data: Optional[Dict[str, Any]] = None
    historical_cutoffs: Optional[Dict[str, Any]] = None

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
            "popularity_available": self.popularity_available,
            "roi_tier": self.roi_tier,
            "evidence_id": self.evidence_id,
            "choice_code": self.choice_code,
        }


def get_category_search_priority(cat_upper: str) -> List[str]:
    """Expand category query into authoritative Maharashtra CAP seat quota aliases."""
    c_up = (cat_upper or "GOPENS").strip().upper()
    if c_up in ("GOPENS", "OPEN", "GENERAL"):
        return ["GOPENS", "GOPENH", "GOPENO", "OPEN", "DEFOPENS", "LOPENH", "LOPENO"]
    elif "OBC" in c_up:
        return [c_up, "GOBCS", "GOBCH", "GOBCO", "OBC", "DEFOBCS", "LOBCS", "LOBCH", "GOPENS", "GOPENH"]
    elif "SC" in c_up and "VJS" not in c_up:
        return [c_up, "GSCS", "GSCH", "GSCO", "SC", "DEFSCS", "LSCS", "LSCH", "GOPENS", "GOPENH"]
    elif "ST" in c_up:
        return [c_up, "GSTS", "GSTH", "GSTO", "ST", "LSTS", "LSTH", "GOPENS", "GOPENH"]
    elif any(k in c_up for k in ("VJ", "NT", "DT")):
        return [c_up, "GNT1S", "GNT1H", "GNT1O", "GNT2S", "GNT2H", "GNT2O", "GNT3S", "GNT3H", "GNT3O", "GVJS", "GVJH", "GOPENS", "GOPENH"]
    elif "EWS" in c_up:
        return ["EWS", "GOPENS", "GOPENH"]
    elif "TFWS" in c_up:
        return ["TFWS", "GOPENS", "GOPENH"]
    return [c_up, "GOPENS", "GOPENH", "GOPENO"]


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
        # Bug-Fix-5: state-wide sentinel
        if loc_clean in ("maharashtra", "mh", "across maharashtra", "in maharashtra",
                         "throughout maharashtra", "all over maharashtra"):
            return True
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
            best_choice_code: Optional[str] = None

            for b in college.get("branches", []):
                raw_b_name = b.get("branch", "")
                if not self.branch_service.matches_requested_branch(raw_b_name, req_branches):
                    continue

                b_res = self.branch_service.resolve_branch(raw_b_name)
                raw_course_code = b.get("course_code") or b.get("choice_code")
                choice_code_val = format_dte_choice_code(
                    raw_course_code=raw_course_code,
                    institute_code=canon_code,
                    branch_name=b_res.canonical_name,
                    category=cat_upper,
                )

                # Look up cutoff for this branch & category using authoritative CAP quota aliases
                search_cats = get_category_search_priority(cat_upper)
                cut_pct = None
                cut_rank = None
                ev_id = None
                matched_cat_name = cat_upper

                # 1. Search in current year college record
                for target_cat in search_cats:
                    for c_entry in b.get("categories", []):
                        if c_entry.get("category", "").upper() == target_cat:
                            cutoffs = c_entry.get("cutoffs", [])
                            if cutoffs:
                                latest_cut = cutoffs[0]
                                cut_pct = latest_cut.get("closing_percentile")
                                cut_rank = latest_cut.get("closing_rank")
                                ev_id = latest_cut.get("evidence_id")
                                matched_cat_name = target_cat
                                break
                    if cut_pct is not None:
                        break

                # 2. Fallback: If not found in current year, check previous available years
                if cut_pct is None and years_map:
                    for prev_yr in sorted(years_map.keys(), reverse=True):
                        if prev_yr == college.get("academic_year"):
                            continue
                        prev_col = years_map[prev_yr]
                        for prev_b in prev_col.get("branches", []):
                            if self.branch_service.matches_requested_branch(prev_b.get("branch", ""), req_branches):
                                for target_cat in search_cats:
                                    for c_entry in prev_b.get("categories", []):
                                        if c_entry.get("category", "").upper() == target_cat:
                                            cutoffs = c_entry.get("cutoffs", [])
                                            if cutoffs:
                                                latest_cut = cutoffs[0]
                                                cut_pct = latest_cut.get("closing_percentile")
                                                cut_rank = latest_cut.get("closing_rank")
                                                ev_id = latest_cut.get("evidence_id")
                                                matched_cat_name = target_cat
                                                break
                                    if cut_pct is not None:
                                        break
                            if cut_pct is not None:
                                break
                        if cut_pct is not None:
                            break

                # If score filter is active, check attainability
                if percentile is not None and cut_pct is not None:
                    # Include if within reasonable discovery window (percentile + 6.0 to -25.0)
                    if cut_pct > percentile + 6.0:
                        continue

                branch_info = DiscoveredBranchInfo(
                    raw_name=raw_b_name,
                    canonical_name=b_res.canonical_name,
                    canonical_group=b_res.canonical_group,
                    latest_cutoff_percentile=cut_pct,
                    latest_closing_rank=cut_rank,
                    round_no=1,
                    academic_year=college.get("academic_year"),
                    evidence_id=ev_id or f"EV-{canon_code}-{matched_cat_name}-R1",
                    seat_category=matched_cat_name,
                    choice_code=choice_code_val,
                    course_code=str(raw_course_code) if raw_course_code else choice_code_val,
                )
                matching_branches.append(branch_info)

                if cut_pct is not None and (best_pct is None or cut_pct > best_pct):
                    best_pct = cut_pct
                    best_rank = cut_rank
                    best_ev_id = ev_id
                    best_choice_code = choice_code_val

            if matching_branches:
                seen_codes.add(canon_code)
                autonomy = "Affiliated"
                if "autonomous" in inst_name.lower():
                    autonomy = "Autonomous"
                elif "government" in inst_name.lower() or "govt" in inst_name.lower():
                    autonomy = "Government"

                final_choice_code = best_choice_code or (matching_branches[0].choice_code if matching_branches else None)

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
                        choice_code=final_choice_code,
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

        # Bug-Fix-6: attach historical cutoffs (all years) for each shortlisted college
        for inst in shortlist:
            code = inst.institute_code
            hist = {}
            yr_map = self.cutoff_agent._by_code.get(code, {})
            for hist_yr, yr_data in sorted(yr_map.items()):
                for br in yr_data.get("branches", []):
                    if not any(req_b.lower() in br.get("branch", "").lower() for req_b in req_branches):
                        continue
                    for cat_d in br.get("categories", []):
                        if cat_d.get("category", "").upper() != cat_upper:
                            continue
                        for cut in cat_d.get("cutoffs", []):
                            yr_key = f"{hist_yr} R{cut.get('round', 1)}"
                            if yr_key not in hist and cut.get("closing_percentile"):
                                hist[yr_key] = {
                                    "closing_percentile": round(float(cut["closing_percentile"]), 4),
                                    "closing_rank": cut.get("closing_rank"),
                                    "evidence_id": cut.get("evidence_id", ""),
                                }
            # Store historical cutoffs as an attribute (dynamic attachment)
            inst.__dict__["historical_cutoffs"] = hist
            inst.historical_cutoffs = hist

            # Attach verified fee, placement, and popularity metrics from CollegeMetricsService
            try:
                from scripts.college_metrics_service import CollegeMetricsService
                cms = CollegeMetricsService.get_instance()
                m_info = cms.get_metrics_for_code(code)
                if not m_info and inst.institute_name:
                    m_info = cms.get_or_enrich_college(code, inst.institute_name, district=inst.district, autonomy_type=inst.autonomy_type)
                if m_info:
                    inst.fee_data = m_info.get("fee_data")
                    inst.placement_data = m_info.get("placement_data")
                    if m_info.get("popularity_signals"):
                        inst.popularity_score = m_info["popularity_signals"].get("overall_score")
                        inst.popularity_available = True
            except Exception:
                pass

        # Step 3: Allied Branch Interleaved Option List
        # Builds a granular preference list where every matching branch in each college
        # is treated as an individual CAP choice option, ranked by cutoff competitiveness.
        interleaved_options: List[Dict[str, Any]] = []
        for inst in discovered_institutes:
            fee_d = getattr(inst, "fee_data", None)
            plc_d = getattr(inst, "placement_data", None)
            for mb in inst.matching_branches:
                tier = "Target"
                if percentile is not None and mb.latest_cutoff_percentile is not None:
                    delta = percentile - mb.latest_cutoff_percentile
                    if delta < -0.5:
                        tier = "Reach"
                    elif -0.5 <= delta <= 2.5:
                        tier = "Target"
                    else:
                        tier = "Safety"

                interleaved_options.append({
                    "institute_code": inst.institute_code,
                    "institute_name": inst.institute_name,
                    "branch_name": mb.canonical_name,
                    "canonical_group": mb.canonical_group,
                    "choice_code": mb.choice_code,
                    "cutoff_percentile": mb.latest_cutoff_percentile,
                    "closing_rank": mb.latest_closing_rank,
                    "tier": tier,
                    "city": inst.city,
                    "district": inst.district,
                    "autonomy_type": inst.autonomy_type,
                    "round_no": mb.round_no,
                    "academic_year": mb.academic_year,
                    "evidence_id": mb.evidence_id,
                    "fee_data": fee_d,
                    "placement_data": plc_d,
                    "popularity_score": inst.popularity_score,
                })

        # Sort interleaved options by cutoff percentile descending
        interleaved_options.sort(
            key=lambda x: x["cutoff_percentile"] if x["cutoff_percentile"] is not None else 0.0,
            reverse=True
        )
        for idx, opt in enumerate(interleaved_options, 1):
            opt["preference_priority"] = idx

        return {
            "status": "success",
            "requested_unique_colleges": limit,
            "total_matching_unique_institutes": total_matching_unique_institutes,
            "returned_count": len(shortlist),
            "location_scope": location or "Maharashtra",
            "preferred_branches": req_branches,
            "colleges": shortlist,
            "interleaved_options": interleaved_options[:limit * 3],
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

