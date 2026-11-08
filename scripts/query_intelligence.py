"""
AI-CON Query Intelligence & Intent Parser (Task 2).
Provides typed, validated query representations with structured entity extraction:
- intent: Typed admission intent
- exam: MHT-CET, JEE, etc.
- percentile, rank
- category (raw user text vs normalized seat token)
- location scope (e.g. Pune district, Pune city, Alandi, Wagholi)
- canonical branches and requested branch count
- requested unique college count (e.g. 30 unique colleges)
- ranking objective: popularity, roi, cutoff, etc.
- follow-up handling with active session context inheritance
"""
from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("aicon.query_intelligence")


class AdmissionIntent(str, Enum):
    COLLEGE_DISCOVERY = "college_discovery"
    CUTOFF_LOOKUP = "cutoff_lookup"
    CUTOFF_TREND = "cutoff_trend"
    COLLEGE_INFORMATION = "college_information"
    COLLEGE_COMPARISON = "college_comparison"
    ROI_RANKING = "roi_ranking"
    POPULATION_RANKING = "popularity_ranking"
    OPTION_FORM_PLANNING = "option_form_planning"
    ML_CUTOFF_PREDICTION = "ml_cutoff_prediction"
    FOLLOW_UP = "follow_up"
    CLARIFICATION_REQUIRED = "clarification_required"


class RankingObjective(str, Enum):
    POPULARITY = "popularity"
    ROI = "roi"
    CUTOFF_PERCENTILE = "cutoff_percentile"
    CLOSING_RANK = "closing_rank"
    BALANCED = "balanced"
    NONE = "none"


# Common geographic districts and municipal areas in Maharashtra
COMMON_LOCATIONS: Dict[str, List[str]] = {
    "pune": ["pune", "alandi", "wagholi", "pimpri", "chinchwad", "hadapsar", "baramati", "talegaon", "lavasa", "bavdhan"],
    "mumbai": ["mumbai", "navi mumbai", "bandra", "andheri", "dadar", "chembur", "matunga", "sion", "borivali", "vile parle"],
    "thane": ["thane", "kalyan", "dombivli", "ulhasnagar", "mumbra", "bhiwandi"],
    "nagpur": ["nagpur", "ramtek", "kamptee"],
    "nashik": ["nashik", "panchavati", "malegaon", "dindori"],
    "amravati": ["amravati", "badnera", "achpur"],
    "aurangabad": ["aurangabad", "chhatrapati sambhajinagar", "chhatrapati-sambhajinagar", "sambhajinagar"],
    "kolhapur": ["kolhapur", "ichalkaranji", "jaysingpur"],
    "sangli": ["sangli", "miraj", "kupwad", "islampur"],
    "solapur": ["solapur", "pandharpur", "barshi"],
    "satara": ["satara", "karad", "wai", "phaltan"],
    "ahmednagar": ["ahmednagar", "shirdi", "kopargaon", "sangamner"],
    "jalgaon": ["jalgaon", "bhusawal", "amalner"],
    "nanded": ["nanded"],
    "latur": ["latur"],
    "dhule": ["dhule"],
    "chandrapur": ["chandrapur"],
    "raigad": ["raigad", "panvel", "alibag"],
}

# Raw Category to normalized CAP Quota token mappings
CATEGORY_NORMALIZATION: Dict[str, str] = {
    "open": "GOPENS",
    "general": "GOPENS",
    "gopens": "GOPENS",
    "lopens": "LOPENS",
    "obc": "GOBCS",
    "gobcs": "GOBCS",
    "lobcs": "LOBCS",
    "sc": "GSCS",
    "gscs": "GSCS",
    "lscs": "LSCS",
    "st": "GSTS",
    "gsts": "GSTS",
    "lsts": "LSTS",
    "vj": "GVJS",
    "nt": "GNT1S",
    "nt1": "GNT1S",
    "nt2": "GNT2S",
    "nt3": "GNT3S",
    "tfws": "TFWS",
    "ews": "EWS",
}

# Canonical branch definitions
CANONICAL_BRANCH_MAP: Dict[str, str] = {
    "computer engineering": "Computer Engineering",
    "computer science": "Computer Engineering",
    "computer science and engineering": "Computer Science and Engineering",
    "cse": "Computer Science and Engineering",
    "comp": "Computer Engineering",
    "information technology": "Information Technology",
    "it": "Information Technology",
    "artificial intelligence": "Artificial Intelligence and Data Science",
    "ai": "Artificial Intelligence and Data Science",
    "ai & ds": "Artificial Intelligence and Data Science",
    "ai and ds": "Artificial Intelligence and Data Science",
    "data science": "Computer Science and Engineering (Data Science)",
    "aiml": "Computer Science and Engineering(Artificial Intelligence and Machine Learning)",
    "ai & ml": "Computer Science and Engineering(Artificial Intelligence and Machine Learning)",
    "mechanical": "Mechanical Engineering",
    "mechanical engineering": "Mechanical Engineering",
    "civil": "Civil Engineering",
    "civil engineering": "Civil Engineering",
    "electrical": "Electrical Engineering",
    "electrical engineering": "Electrical Engineering",
    "entc": "Electronics and Telecommunication Engg",
    "electronics": "Electronics and Telecommunication Engg",
    "electronics and telecommunication": "Electronics and Telecommunication Engg",
}


class ParsedAdmissionQuery(BaseModel):
    raw_query: str
    intent: AdmissionIntent
    exam: Optional[str] = None  # e.g. "MHT-CET", "JEE"
    percentile: Optional[float] = None
    rank: Optional[int] = None
    category_raw: Optional[str] = None
    normalized_seat_code: Optional[str] = None
    location: Optional[str] = None
    location_scope_notes: Optional[str] = None
    preferred_branches: List[str] = Field(default_factory=list)
    requested_unique_colleges: Optional[int] = None
    ranking_objective: RankingObjective = RankingObjective.NONE
    academic_year: Optional[str] = None
    cap_round: Optional[int] = None
    is_multi_college: bool = False
    is_follow_up: bool = False
    target_college: Optional[str] = None
    ambiguities: List[str] = Field(default_factory=list)

    @field_validator("percentile")
    @classmethod
    def validate_percentile(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError(f"Percentile must be between 0.0 and 100.0, got {v}")
        return v

    @field_validator("rank")
    @classmethod
    def validate_rank(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError(f"Merit rank must be >= 1, got {v}")
        return v

    @field_validator("requested_unique_colleges")
    @classmethod
    def validate_requested_count(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            return 1
        return v

    def to_dict(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["intent"] = self.intent.value
        d["ranking_objective"] = self.ranking_objective.value
        return d


class QueryIntelligenceParser:
    """
    Typed natural language query intelligence parser for Maharashtra engineering admissions.
    Combines rule-based deterministic parsing, entity extraction, boundary validation,
    and optional LLM-assisted disambiguation.
    """

    def __init__(self, llm_callable: Optional[Callable[[str, str], str]] = None):
        self.llm_callable = llm_callable

    def parse_query(
        self,
        query: str,
        conversation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Parse query string and return backward-compatible dictionary representation."""
        parsed_obj = self.parse_admission_query(query, conversation_context)
        res = parsed_obj.to_dict()
        # Ensure backward compatibility with orchestrator expectation keys
        res["category"] = parsed_obj.normalized_seat_code or parsed_obj.category_raw
        # Map intent to orchestrator string if needed
        if parsed_obj.intent == AdmissionIntent.COLLEGE_DISCOVERY:
            res["intent"] = "multi_college_discovery"
        elif parsed_obj.intent in (AdmissionIntent.CUTOFF_LOOKUP, AdmissionIntent.CUTOFF_TREND):
            res["intent"] = "cutoff_analysis"
        elif parsed_obj.intent == AdmissionIntent.ROI_RANKING:
            res["intent"] = "reputation_roi_ranking"
        elif parsed_obj.intent == AdmissionIntent.POPULATION_RANKING:
            res["intent"] = "multi_college_discovery"
        return res

    def parse_admission_query(
        self,
        query: str,
        conversation_context: Optional[Dict[str, Any]] = None,
    ) -> ParsedAdmissionQuery:
        """Parse query string into a strictly typed ParsedAdmissionQuery."""
        q_lower = query.lower().strip()
        context = conversation_context or {}

        # 1. Follow-up query detection
        is_follow_up = False
        follow_up_tokens = [
            "these colleges", "of these", "show their", "rank these", "rank them",
            "sort them", "which of these", "for them", "their cutoffs", "their placement",
            "include placement", "show only pune", "give me 30 colleges", "show 30 instead",
            "change my percentile", "rank by roi", "rank by popularity", "give me list of",
            "list of 30", "show 30"
        ]
        has_prior_shortlist = bool(context.get("last_shortlist"))
        has_prior_context = bool(context.get("percentile") or context.get("location") or context.get("last_query"))
        if has_prior_shortlist or has_prior_context:
            if any(tok in q_lower for tok in follow_up_tokens) or q_lower.startswith(("now ", "then ", "instead ", "also ", "give me ", "show ")):
                is_follow_up = True
            elif "30 colleges" in q_lower or "list of 30" in q_lower or "rank these" in q_lower:
                is_follow_up = True

        # 2. Extract Requested Unique College Count (e.g., "30 colleges", "top 10")
        requested_count: Optional[int] = None
        m_count = re.search(r"\b(?:top\s+|list\s+of\s+|best\s+|most\s+popular\s+)?(\d{1,3})\s+(?:unique\s+)?colleges?\b", q_lower)
        if m_count:
            try:
                requested_count = int(m_count.group(1))
            except ValueError:
                pass
        elif is_follow_up and re.search(r"\b(?:give\s+me|show)\s+(\d{1,3})\b", q_lower):
            m_num = re.search(r"\b(\d{1,3})\b", q_lower)
            if m_num:
                requested_count = int(m_num.group(1))

        # 3. Extract Exam
        exam = None
        if "cet" in q_lower or "mht-cet" in q_lower or "mhtcet" in q_lower:
            exam = "MHT-CET"
        elif "jee" in q_lower or "jee-main" in q_lower:
            exam = "JEE"

        # 4. Extract Percentile
        percentile: Optional[float] = None
        m_perc = re.search(r"(\d+(?:\.\d+)?)\s*(?:percentile|%|pr\b)", q_lower)
        if not m_perc:
            m_perc = re.search(r"\b(?:percentile|score|pct)\s*(?:is|=|of|to)?\s*(\d+(?:\.\d+)?)\b", q_lower)
        if m_perc:
            try:
                p_val = float(m_perc.group(1))
                if 0.0 <= p_val <= 100.0:
                    percentile = p_val
            except ValueError:
                pass
        elif is_follow_up and context.get("percentile") is not None:
            percentile = context.get("percentile")

        # 5. Extract Merit Rank
        rank: Optional[int] = None
        m_rank = re.search(r"(?:merit\s+)?rank\s*(?:is|=|of|:)?\s*([\d,]+)", q_lower)
        if m_rank:
            try:
                r_val = int(m_rank.group(1).replace(",", ""))
                if r_val >= 1:
                    rank = r_val
            except ValueError:
                pass
        elif is_follow_up and context.get("rank") is not None:
            rank = context.get("rank")

        # 6. Extract Category
        category_raw: Optional[str] = None
        normalized_seat: Optional[str] = None
        m_cat = re.search(r"\bcategory\s+([A-Za-z0-9_-]+)\b", q_lower)
        if m_cat:
            category_raw = m_cat.group(1).upper()
        else:
            for raw_c in CATEGORY_NORMALIZATION:
                if re.search(r"\b" + re.escape(raw_c) + r"\b", q_lower):
                    category_raw = raw_c.upper()
                    break

        if category_raw:
            normalized_seat = CATEGORY_NORMALIZATION.get(category_raw.lower(), category_raw)
        elif is_follow_up and context.get("category"):
            category_raw = context.get("category")
            normalized_seat = CATEGORY_NORMALIZATION.get(category_raw.lower(), category_raw)

        # 7. Extract Location and Geographic Scope
        location: Optional[str] = None
        scope_notes: Optional[str] = None
        for dist_key, aliases in COMMON_LOCATIONS.items():
            for alias in aliases:
                if re.search(r"\b" + re.escape(alias) + r"\b", q_lower):
                    location = dist_key.capitalize()
                    if alias in ("alandi", "wagholi", "pimpri", "chinchwad"):
                        scope_notes = f"Matched locality '{alias.capitalize()}' within Pune district scope."
                    elif alias in ("navi mumbai", "bandra", "andheri", "dadar"):
                        scope_notes = f"Matched locality '{alias.capitalize()}' within Mumbai metropolitan scope."
                    break
            if location:
                break

        if not location and is_follow_up and context.get("location"):
            location = context.get("location")
            scope_notes = context.get("location_scope_notes")

        # 8. Extract Branches
        preferred_branches: List[str] = []
        for branch_alias, canonical in CANONICAL_BRANCH_MAP.items():
            if re.search(r"\b" + re.escape(branch_alias) + r"\b", q_lower):
                if canonical not in preferred_branches:
                    preferred_branches.append(canonical)

        # Handle "and related branches" pattern
        if "related branches" in q_lower or "all related" in q_lower:
            if "Computer Engineering" in preferred_branches or "Computer Science and Engineering" in preferred_branches:
                for rel in [
                    "Information Technology",
                    "Artificial Intelligence and Data Science",
                    "Computer Science and Engineering(Artificial Intelligence and Machine Learning)",
                    "Computer Science and Engineering (Data Science)",
                ]:
                    if rel not in preferred_branches:
                        preferred_branches.append(rel)

        if not preferred_branches and is_follow_up and context.get("preferred_branches"):
            preferred_branches = list(context.get("preferred_branches"))

        # Default fallback branch for multi-college engineering discovery
        if not preferred_branches and (requested_count or "colleges" in q_lower):
            preferred_branches = ["Computer Engineering"]

        # 9. Extract Ranking Objective
        ranking_obj = RankingObjective.NONE
        if any(k in q_lower for k in ["popular", "popularity", "most popular", "demand"]):
            ranking_obj = RankingObjective.POPULARITY
        elif any(k in q_lower for k in ["roi", "return on investment", "value for money"]):
            ranking_obj = RankingObjective.ROI
        elif "rank" in q_lower and "by rank" in q_lower:
            ranking_obj = RankingObjective.CLOSING_RANK
        elif is_follow_up and context.get("ranking_objective"):
            ranking_obj = RankingObjective(context.get("ranking_objective"))

        # 10. Extract Academic Year and Round
        academic_year = None
        m_year = re.search(r"\b(202[0-6](?:-[0-2][0-9])?)\b", query)
        if m_year:
            y_str = m_year.group(1)
            academic_year = y_str if "-" in y_str else f"{y_str}-{str(int(y_str[-2:]) + 1).zfill(2)}"

        cap_round = None
        m_round = re.search(r"\b(?:cap\s*|round\s*)([1-4])\b", q_lower)
        if m_round:
            cap_round = int(m_round.group(1))

        # 11. Multi-College flag & Intent Determination
        multi_college_indicators = [
            "list of", "list of 30", "30 colleges", "colleges in", "list colleges",
            "give me colleges", "give me a list", "suggest colleges", "which colleges",
            "options for", "chances in", "shortlist", "colleges for", "recommend colleges"
        ]
        is_multi_college = (
            requested_count is not None
            or any(trig in q_lower for trig in multi_college_indicators)
            or (percentile is not None and not any(k in q_lower for k in ["predict", "regressor"]))
            or (is_follow_up and bool(context.get("last_shortlist")))
        )

        # Intent Classification
        if is_follow_up:
            if ranking_obj == RankingObjective.ROI:
                intent = AdmissionIntent.ROI_RANKING
            elif ranking_obj == RankingObjective.POPULARITY:
                intent = AdmissionIntent.POPULATION_RANKING
            elif any(k in q_lower for k in ["trend", "history", "years", "cutoffs change"]):
                intent = AdmissionIntent.CUTOFF_TREND
            else:
                intent = AdmissionIntent.COLLEGE_DISCOVERY
        elif any(k in q_lower for k in ["predict", "histgradientboosting", "regressor", "ml model"]):
            intent = AdmissionIntent.ML_CUTOFF_PREDICTION
        elif ranking_obj == RankingObjective.ROI:
            intent = AdmissionIntent.ROI_RANKING
        elif ranking_obj == RankingObjective.POPULARITY and is_multi_college:
            intent = AdmissionIntent.COLLEGE_DISCOVERY
        elif any(k in q_lower for k in ["option form", "preference form", "preference list"]):
            intent = AdmissionIntent.OPTION_FORM_PLANNING
        elif any(k in q_lower for k in ["trend", "progression", "compare years", "across years"]):
            intent = AdmissionIntent.CUTOFF_TREND
        elif is_multi_college:
            intent = AdmissionIntent.COLLEGE_DISCOVERY
        elif any(k in q_lower for k in ["cutoff", "closing rank", "percentile"]) and not is_multi_college:
            intent = AdmissionIntent.CUTOFF_LOOKUP
        elif any(k in q_lower for k in ["fee", "fees", "hostel", "naac", "nirf", "placement", "address", "affiliation"]):
            intent = AdmissionIntent.COLLEGE_INFORMATION
        else:
            intent = AdmissionIntent.COLLEGE_INFORMATION

        # Check Ambiguities
        ambiguities = []
        if intent == AdmissionIntent.COLLEGE_DISCOVERY and not location and not percentile and not rank:
            ambiguities.append("No location or score provided for discovery.")

        return ParsedAdmissionQuery(
            raw_query=query,
            intent=intent,
            exam=exam,
            percentile=percentile,
            rank=rank,
            category_raw=category_raw,
            normalized_seat_code=normalized_seat,
            location=location,
            location_scope_notes=scope_notes,
            preferred_branches=preferred_branches,
            requested_unique_colleges=requested_count,
            ranking_objective=ranking_obj,
            academic_year=academic_year,
            cap_round=cap_round,
            is_multi_college=is_multi_college,
            is_follow_up=is_follow_up,
            target_college=None,
            ambiguities=ambiguities,
        )
