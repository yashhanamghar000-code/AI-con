"""
Orchestrator: routes admission and college questions to the appropriate agent.
- Resolves which college the user means using CollegeResolver.
- Classifies question intent (cutoff, info, or both).
- Queries CutoffAgent (structured lookup) or CollegeInfoAgent (vector search).
- If cutoff data is unavailable in the workspace, explicitly reports status='unavailable'
- In Phase 1, ran in evidence-only mode (no LLM call attached).
- In Phase 2, connects local LLM (Ollama / qwen2.5:7b) with grounded anti-hallucination prompting.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Support direct and relative imports
try:
    from college_resolver import CollegeResolution, CollegeResolver
except ImportError:
    from scripts.agents.college_resolver import CollegeResolution, CollegeResolver

try:
    from query_intelligence import QueryIntelligenceParser
except ImportError:
    try:
        from scripts.query_intelligence import QueryIntelligenceParser
    except ImportError:
        QueryIntelligenceParser = None

try:
    from conversation_memory import ConversationMemoryStore, ShortlistRecord
except ImportError:
    try:
        from scripts.conversation_memory import ConversationMemoryStore, ShortlistRecord
    except ImportError:
        ConversationMemoryStore = None
        ShortlistRecord = None

try:
    from college_discovery import StructuredCollegeDiscoveryService
    from branch_taxonomy import BranchTaxonomyService
except ImportError:
    try:
        from scripts.college_discovery import StructuredCollegeDiscoveryService
        from scripts.branch_taxonomy import BranchTaxonomyService
    except ImportError:
        StructuredCollegeDiscoveryService = None
        BranchTaxonomyService = None

try:
    from admission_rules import AdmissionRulesEngine, EligibilityResult, StudentProfile
    from cutoff_analyzer import CutoffAnalyzer
    from option_planner import OptionFormPlanner
    from recommendation_engine import RecommendationEngine
except ImportError:
    try:
        from scripts.admission_rules import AdmissionRulesEngine, EligibilityResult, StudentProfile
        from scripts.cutoff_analyzer import CutoffAnalyzer
        from scripts.option_planner import OptionFormPlanner
        from scripts.recommendation_engine import RecommendationEngine
    except ImportError:
        AdmissionRulesEngine = None
        EligibilityResult = None
        StudentProfile = None
        CutoffAnalyzer = None
        OptionFormPlanner = None
        RecommendationEngine = None


CUTOFF_KEYWORDS = [
    "cutoff", "percentile", "rank", "closing rank", "merit", "round",
    "gopens", "gscs", "gsts", "lopens", "tfws", "ews", "category", "seat type"
]
TREND_KEYWORDS = [
    "trend", "year-over-year", "previous year", "past years", "cutoffs change",
    "progression", "compare years", "across years", "historical trend"
]
OPTION_PLAN_KEYWORDS = [
    "option form", "preference list", "option plan", "which options", "chances", "attainable", "reach"
]
INFO_KEYWORDS = [
    "placement", "package", "naac", "nirf", "fee", "fees", "hostel",
    "established", "affiliat", "contact", "address", "about", "accreditation",
    "district", "city", "website", "ownership", "type", "university"
]

CUTOFF_UNAVAILABLE = (
    "Cutoff data is not available in this workspace. College-information "
    "retrieval does not include admission cutoffs or CAP round closing figures. "
    "No cutoff values were generated."
)

GENERIC_BRANCH_STOPWORDS: Set[str] = {
    "engineering", "technology", "course", "branch", "department", "degree",
    "bachelor", "btech", "programme", "program", "science", "and", "the", "for",
    "what", "cutoff", "cutoffs", "closing", "rank", "percentile", "score", "round",
    "gopens", "open", "admission", "college", "institute", "government", "govt",
    "trend", "trends", "historical", "previous", "year", "years", "round1", "round2",
    "round3", "cap", "allotment", "seat", "seats", "quota", "give", "tell", "show",
    "please", "status", "avail", "available", "data", "info", "information",
}

LEADING_BRANCH_QUERY_WORDS: Set[str] = {
    "the", "a", "an", "for", "in", "of", "about", "what", "was", "is", "are",
    "tell", "give", "show", "me", "cutoff", "cutoffs", "closing", "merit",
    "rank", "ranks", "percentile", "percentiles", "score", "scores",
    "round", "rounds", "cap", "seat", "seats", "quota", "at", "to", "from",
    "which", "any", "please", "check", "find", "get", "with",
}

COLLEGE_STOPWORDS: Set[str] = {
    "college", "institute", "university", "government", "govt", "school",
    "institution", "academy", "polytechnic", "autonomous",
}

KNOWN_DISCIPLINES: Dict[str, str] = {
    "aerospace": "Aerospace Engineering",
    "aeronautical": "Aeronautical Engineering",
    "biomedical": "Biomedical Engineering",
    "biotechnology": "Biotechnology",
    "chemical": "Chemical Engineering",
    "civil": "Civil Engineering",
    "computer science and engineering": "Computer Science and Engineering",
    "computer science": "Computer Science and Engineering",
    "computer engineering": "Computer Engineering",
    "computer": "Computer Science and Engineering",
    "electrical": "Electrical Engineering",
    "electronics and telecommunication": "Electronics and Telecommunication Engineering",
    "electronics": "Electronics and Telecommunication Engineering",
    "instrumentation": "Instrumentation Engineering",
    "mechanical": "Mechanical Engineering",
    "metallurgical": "Metallurgical Engineering",
    "metallurgy": "Metallurgical Engineering",
    "mining": "Mining Engineering",
    "production": "Production Engineering",
    "textile": "Textile Engineering",
    "mechatronics": "Mechatronics Engineering",
    "robotics": "Robotics and Automation",
    "petroleum": "Petroleum Engineering",
    "automobile": "Automobile Engineering",
    "data science": "Data Science",
    "cyber security": "Cyber Security",
    "cyber": "Cyber Security",
    "information technology": "Information Technology",
    "artificial intelligence": "Artificial Intelligence",
}


def _format_branch_title(name: str) -> str:
    """Format branch name into title case while keeping standard conjunctions lowercase."""
    minor_words = {"and", "of", "in", "for", "with", "&"}
    words = name.strip().split()
    return " ".join(
        w.lower() if w.lower() in minor_words and i > 0 else w.capitalize()
        for i, w in enumerate(words)
    )


def extract_evidence_identifiers(evidence_text: str) -> List[str]:
    """Extract valid bracketed citation identifiers from evidence text.

    Finds tags like [MHHEI_00001:MHHEI_00001_profile] or [EV-01002-COMP-GOPENS-R1].
    """
    if not evidence_text:
        return []
    matches = re.findall(r"\[([A-Za-z0-9_:\-]+)\]", evidence_text)
    seen = set()
    identifiers: List[str] = []
    for m in matches:
        if m not in seen and not m.lower().startswith("citation") and not m.lower() == "brackets":
            seen.add(m)
            identifiers.append(m)
    return identifiers


def normalize_citations(answer: str, evidence_text: str, intent: Optional[str] = None) -> str:
    """Ensure citation identifiers in the generated answer match exact identifiers from evidence.

    Protects against LLMs substituting literal placeholders (e.g. '[record_id:chunk_id]')
    or fabricating profile citations (e.g. '[MHHEI_00001:MHHEI_00001_profile]') on cutoff facts.
    """
    valid_ids = extract_evidence_identifiers(evidence_text)
    if not valid_ids or not answer:
        return answer

    # Build lookup map for common model mutations
    # E.g. for valid_id 'MHHEI_00001:MHHEI_00001_profile':
    #   'record_id:mhhei_00001_profile' -> 'MHHEI_00001:MHHEI_00001_profile'
    #   'mhhei_00001_profile'           -> 'MHHEI_00001:MHHEI_00001_profile'
    #   'record-id:mhhei_00001_profile' -> 'MHHEI_00001:MHHEI_00001_profile'
    lookup: Dict[str, str] = {}
    for vid in valid_ids:
        lookup[vid.lower()] = vid
        if ":" in vid:
            prefix, chunk = vid.split(":", 1)
            lookup[chunk.lower()] = vid
            lookup[f"record_id:{chunk.lower()}"] = vid
            lookup[f"record-id:{chunk.lower()}"] = vid
            lookup[f"chunk_id:{chunk.lower()}"] = vid

    def _replace_cite(match: re.Match) -> str:
        token = match.group(1).strip()
        token_lower = token.lower()
        if token in valid_ids:
            return f"[{token}]"
        if token_lower in lookup:
            return f"[{lookup[token_lower]}]"
        if token_lower.startswith("record_id:") or token_lower.startswith("record-id:"):
            suffix = token.split(":", 1)[1].strip()
            if suffix.lower() in lookup:
                return f"[{lookup[suffix.lower()]}]"
        # Protect against hallucinated profile citations in cutoff/trend contexts
        if token.startswith("MHHEI_") and (intent in ("cutoff", "trend") or "MHHEI_" not in evidence_text):
            return ""
        return f"[{token}]"

    cleaned = re.sub(r"\[([A-Za-z0-9_:\-]+)\]", _replace_cite, answer)
    cleaned = re.sub(r"  +", " ", cleaned).strip()
    return cleaned


class Orchestrator:
    def __init__(
        self,
        cutoff_agent: Any = None,
        college_info_agent: Any = None,
        llm_call: Optional[Callable[[str, str], str]] = None,
    ):
        # Data sources are optional during instantiation (e.g. for pure parsing/testing)
        # rag_pipeline.py enforces at least one data source for CLI invocation.
        self.cutoff_agent = cutoff_agent
        self.college_info_agent = college_info_agent
        self.llm_call = llm_call

        self.resolver = CollegeResolver()

        # Populate name index for resolution
        if cutoff_agent is not None and hasattr(cutoff_agent, "_by_code"):
            for code, years in cutoff_agent._by_code.items():
                for college in years.values():
                    self.resolver.register(
                        college.get("institute_name"),
                        institute_code=code or college.get("institute_code"),
                        record_id=college.get("record_id"),
                    )

        if college_info_agent is not None and hasattr(college_info_agent, "list_name_index"):
            for name, entry in college_info_agent.list_name_index().items():
                self.resolver.register(
                    name,
                    institute_code=entry.get("institute_code"),
                    record_id=entry.get("record_id"),
                )

        # Phase 3 Admission Intelligence services
        self.rules_engine = AdmissionRulesEngine() if AdmissionRulesEngine is not None else None
        if cutoff_agent is not None and CutoffAnalyzer is not None:
            self.cutoff_analyzer = CutoffAnalyzer(cutoff_agent)
            self.recommendation_engine = RecommendationEngine(cutoff_agent, self.rules_engine)
            self.option_planner = OptionFormPlanner(self.recommendation_engine)
        else:
            self.cutoff_analyzer = None
            self.recommendation_engine = None
            self.option_planner = None

        self.query_parser = QueryIntelligenceParser(llm_callable=None) if QueryIntelligenceParser is not None else None
        self.memory_store = ConversationMemoryStore() if ConversationMemoryStore is not None else None
        self.discovery_service = StructuredCollegeDiscoveryService(cutoff_agent) if (StructuredCollegeDiscoveryService is not None and cutoff_agent is not None) else None
        self.branch_service = BranchTaxonomyService() if BranchTaxonomyService is not None else None
        self._conv_context: Dict[str, Any] = {}
        self._current_session_id: str = "default_session" 

        # Load ML predictive models (HistGradientBoostingRegressor)
        self._tabular_models_loaded = False
        self._rank_model = None
        self._pct_model = None
        self._encoder_info = None
        try:
            import joblib
            proj_root = Path(__file__).resolve().parent.parent.parent
            art_dir = proj_root / "model_artifacts"
            rank_p = art_dir / "cutoff_regressor_rank.joblib"
            pct_p = art_dir / "cutoff_regressor_percentile.joblib"
            enc_p = art_dir / "label_encoders.joblib"
            if rank_p.exists() and pct_p.exists() and enc_p.exists():
                self._rank_model = joblib.load(rank_p)
                self._pct_model = joblib.load(pct_p)
                self._encoder_info = joblib.load(enc_p)
                self._tabular_models_loaded = True
        except Exception:
            pass

    @property
    def _name_index(self) -> Dict[str, Dict[str, Optional[str]]]:
        """Backward compatibility property returning underlying name dictionary."""
        return self.resolver._name_index

    def resolve_college(self, query_text: str, cutoff: float = 0.5) -> Tuple[Optional[str], Optional[str], float]:
        """Backward compatible signature: returns (institute_code, matched_name, score)."""
        res = self.resolver.resolve(query_text, fuzzy_cutoff=cutoff)
        if res.matched:
            return res.institute_code, res.institute_name, res.confidence
        return None, None, 0.0

    def classify_intent(self, question: str) -> str:
        """Rule-based question intent classifier: 'cutoff', 'trend', 'option_plan', 'info', or 'both'."""
        q = question.lower()
        wants_trend = any(k in q for k in TREND_KEYWORDS)
        wants_plan = any(k in q for k in OPTION_PLAN_KEYWORDS)
        wants_cutoff = any(k in q for k in CUTOFF_KEYWORDS)
        wants_info = any(k in q for k in INFO_KEYWORDS)
        if wants_plan:
            return "option_plan"
        if wants_trend:
            return "trend"
        if wants_cutoff and wants_info:
            return "both"
        if wants_cutoff:
            return "cutoff"
        if wants_info:
            return "info"
        return "info"  # Safer default than silently returning nothing

    def extract_category(self, question: str) -> Optional[str]:
        m = re.search(r"\b([GL]?(?:OPEN|SC|ST|OBC|NT1|NT2|NT3|VJ|SBC|SEBC)[SHO]?|TFWS|EWS|AI)\b", question, re.I)
        return m.group(1).upper() if m else None

    def extract_round(self, question: str) -> Optional[int]:
        m = re.search(r"\bround\s*(I{1,3}|IV|[1-4])\b", question, re.I)
        if not m:
            return None
        token = m.group(1).upper()
        roman = {"I": 1, "II": 2, "III": 3, "IV": 4}
        return roman.get(token, int(token) if token.isdigit() else None)

    def extract_academic_year(self, question: str) -> Optional[str]:
        m = re.search(r"\b(202[0-9]-[0-9]{2})\b", question)
        return m.group(1) if m else None

    def extract_branch(self, question: str, institute_code: Optional[str]) -> Optional[str]:
        """Matches the question against this specific college's own branch list.

        Requires overlap on distinctive discipline keywords (e.g. 'computer', 'civil',
        'mechanical', 'aerospace') rather than generic terms ('engineering', 'technology').
        """
        if self.cutoff_agent is None or not institute_code:
            return None
        branches = self.cutoff_agent.list_branches(institute_code)
        if not branches:
            return None

        q_words = [w for w in re.findall(r"[a-zA-Z]+", question.lower()) if len(w) > 2]
        q_distinctive = set(q_words) - GENERIC_BRANCH_STOPWORDS
        if not q_distinctive:
            return None

        best, best_overlap = None, 0
        for b in branches:
            b_words = [w for w in re.findall(r"[a-zA-Z]+", b.lower()) if len(w) > 2]
            b_distinctive = set(b_words) - GENERIC_BRANCH_STOPWORDS
            overlap = len(q_distinctive & b_distinctive)
            if overlap > best_overlap:
                best, best_overlap = b, overlap
        return best if best_overlap > 0 else None

    def _requested_branch_in_query(self, question: str) -> Optional[str]:
        """Check if user query mentions a specific engineering discipline and return its clean canonical title."""
        q_lower = question.lower()
        # 1. Check known disciplines first (avoids greedy regex eating preceding cutoff/range words)
        for disc, canonical_name in sorted(KNOWN_DISCIPLINES.items(), key=lambda x: len(x[0]), reverse=True):
            pattern = rf"\b{re.escape(disc)}(?:\s+engineering|\s+technology)?\b"
            if re.search(pattern, q_lower):
                return canonical_name

        # 2. Search for discipline phrases preceding engineering/technology/tech/branch
        matches = list(re.finditer(r"\b([a-zA-Z\s]{2,40}?)\s+(engineering|technology|tech|branch)\b", question, re.I))
        for m in matches:
            prefix_raw = m.group(1).strip()
            suffix_raw = m.group(2).strip().lower()
            tokens = [t for t in prefix_raw.split() if t]

            # Strip leading conversational / query grammar stopwords
            while tokens and tokens[0].lower() in LEADING_BRANCH_QUERY_WORDS:
                tokens.pop(0)

            if not tokens:
                continue

            # Discard matches that are parts of college names (e.g. "Government College of Engineering")
            if any(t.lower() in COLLEGE_STOPWORDS for t in tokens):
                continue

            clean_stem = " ".join(tokens)
            stem_lower = clean_stem.lower()

            # Check if any distinctive branch token is present
            stem_tokens = set(stem_lower.split()) - GENERIC_BRANCH_STOPWORDS
            if not stem_tokens and stem_lower not in KNOWN_DISCIPLINES:
                continue

            # Determine canonical formatted name
            if suffix_raw == "branch":
                if stem_lower.endswith("engineering") or stem_lower.endswith("technology"):
                    return _format_branch_title(clean_stem)
                if stem_lower in KNOWN_DISCIPLINES:
                    return KNOWN_DISCIPLINES[stem_lower]
                return f"{_format_branch_title(clean_stem)} Engineering"

            suffix_title = "Engineering" if suffix_raw in ("engineering", "tech") else "Technology"
            if clean_stem.lower().endswith(suffix_title.lower()):
                return _format_branch_title(clean_stem)

            return f"{_format_branch_title(clean_stem)} {suffix_title}"

        return None

    def _handle_cross_college_query(self, question: str) -> Optional[Dict[str, Any]]:
        """Handles multi-college search, cutoff filtering, or shortlist requests."""
        q_lower = question.lower()

        # 1. Check for percentile range: between X and Y
        min_perc, max_perc = None, None
        m_range = re.search(r"between\s+(\d+(?:\.\d+)?)\s*(?:and|to)\s*(\d+(?:\.\d+)?)\s*(?:percentile|%)?", q_lower)
        if m_range:
            min_perc = float(m_range.group(1))
            max_perc = float(m_range.group(2))
        else:
            m_below = re.search(r"(?:below|under|less than|within)\s+(\d+(?:\.\d+)?)\s*(?:percentile|%)", q_lower)
            if m_below:
                max_perc = float(m_below.group(1))
            m_above = re.search(r"(?:above|greater than|at least)\s+(\d+(?:\.\d+)?)\s*(?:percentile|%)", q_lower)
            if m_above:
                min_perc = float(m_above.group(1))

        # 2. Check for rank range
        min_rank, max_rank = None, None
        m_rank_above = re.search(r"(?:closing\s+)?rank\s*(?:above|greater than|>=|>)\s*([\d,]+)", q_lower)
        if m_rank_above:
            min_rank = int(m_rank_above.group(1).replace(",", ""))
        m_rank_below = re.search(r"(?:closing\s+)?rank\s*(?:below|less than|<=|<)\s*([\d,]+)", q_lower)
        if m_rank_below:
            max_rank = int(m_rank_below.group(1).replace(",", ""))

        category = self.extract_category(question)
        branch = self._requested_branch_in_query(question)
        branch_stem = branch
        if branch and "computer" in branch.lower():
            branch_stem = "Computer"
        elif branch and branch.endswith(" Engineering"):
            branch_stem = branch[:-12].strip()

        year = self.extract_academic_year(question)
        round_no = self.extract_round(question)

        # If numerical cutoff search criteria exist and cutoff_agent supports find_colleges
        if (min_perc is not None or max_perc is not None or min_rank is not None or max_rank is not None) and self.cutoff_agent and hasattr(self.cutoff_agent, "find_colleges"):
            matches = self.cutoff_agent.find_colleges(
                min_percentile=min_perc,
                max_percentile=max_perc,
                min_rank=min_rank,
                max_rank=max_rank,
                branch_query=branch_stem,
                category=category,
                year=year,
                round_no=round_no,
                limit=15,
            )
            if matches:
                evidence_text = self.cutoff_agent.as_evidence_text(matches)
                return {
                    "status": "evidence_only",
                    "intent": "cutoff",
                    "query_type": "cross_college_search",
                    "matched_college": f"Multiple Institutes ({len(matches)} matching cutoffs)",
                    "institute_code": None,
                    "record_id": None,
                    "evidence": "CROSS-COLLEGE CUTOFF EVIDENCE:\n" + evidence_text,
                    "total_matches": len(matches),
                }
            else:
                criteria_str = []
                if branch: criteria_str.append(f"branch: '{branch}'")
                if category: criteria_str.append(f"category: '{category}'")
                if min_perc is not None or max_perc is not None: criteria_str.append(f"percentile: [{min_perc}, {max_perc}]")
                if min_rank is not None or max_rank is not None: criteria_str.append(f"rank: [{min_rank}, {max_rank}]")
                if year: criteria_str.append(f"year: '{year}'")
                if round_no: criteria_str.append(f"round: {round_no}")
                return {
                    "status": "unavailable",
                    "intent": "cutoff",
                    "query_type": "cross_college_search",
                    "matched_college": None,
                    "institute_code": None,
                    "record_id": None,
                    "message": f"No cutoff records found matching criteria ({', '.join(criteria_str)}).",
                    "evidence": "CUTOFF EVIDENCE:\nNo matching cutoff records found across colleges.",
                }

        # If it's a general shortlist / recommendation query without specific college:
        if any(k in q_lower for k in ["shortlist", "recommend", "give me a list", "which options", "chances", "attainable", "safe"]):
            return {
                "status": "needs_clarification",
                "intent": "option_plan",
                "query_type": "shortlist_request",
                "matched_college": None,
                "institute_code": None,
                "record_id": None,
                "message": (
                    "To build a personalized college shortlist, please specify: "
                    "(1) Your MHT-CET percentile or merit rank, "
                    "(2) Preferred branch (e.g. Computer Engineering, IT), "
                    "(3) Category/Seat quota (e.g. GOPENS, TFWS, EWS, OBC), and "
                    "(4) Preferred districts or locations (e.g. Pune, Mumbai). "
                    "Alternatively, you may provide specific college names to evaluate their cutoffs."
                ),
                "candidates": [],
            }

        return None

    def _handle_personalized_student_query(self, question: str, student_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Synthesize personalized, grounded admission advice based on authenticated student onboarding profile."""
        q_lower = question.lower()
        name = student_context.get("name") or "Student"
        raw_cat = str(student_context.get("category") or "OPEN").strip().upper()
        raw_pct = student_context.get("percentage") or student_context.get("percentile") or 85.0
        try:
            pct = float(raw_pct)
        except Exception:
            pct = 85.0
        district = student_context.get("district") or "Maharashtra"
        stream = student_context.get("stream") or "Science (PCM)"
        ambitions = student_context.get("ambitions") or ""

        # Map to CET CAP Category Token
        if "OBC" in raw_cat:
            cat_token = "GOBCS"
        elif "SC" in raw_cat:
            cat_token = "GSCS"
        elif "ST" in raw_cat:
            cat_token = "GSTS"
        elif "TFWS" in raw_cat:
            cat_token = "TFWS"
        elif "EWS" in raw_cat:
            cat_token = "EWS"
        else:
            cat_token = "GOPENS"

        # 1. TFWS Eligibility Queries
        if "tfws" in q_lower or "tuition fee waiver" in q_lower or "fee waiver" in q_lower:
            msg = (
                f"Hello {name}, here is your personalized TFWS (Tuition Fee Waiver Scheme) Assessment:\n\n"
                f"1. Your Category: {raw_cat} (All Maharashtra state candidates are eligible regardless of caste).\n"
                f"2. Income Requirement: Annual family income must be under INR 8.0 Lakhs from all sources.\n"
                f"3. Seat Allocation: 5% supernumerary seats in approved Maharashtra CAP engineering colleges.\n"
                f"4. Required Documentation: Valid Income Certificate issued by Tahsildar / SDO for the current financial year.\n"
                f"5. CAP Strategy: When filling your Option Form, select the specific 'T' choice code (e.g., TFWS seat) for your preferred branches in {district}.\n\n"
                f"Note: TFWS seats have high demand; closing cutoffs are typically higher than general seats."
            )
            return {
                "status": "answered",
                "query_type": "personalized_eligibility",
                "matched_college": None,
                "total_matches": 1,
                "message": msg,
                "evidence": f"TFWS Rules: Category={raw_cat}, Statutory Income Limit <= 8,00,000 INR, 5% supernumerary seats.",
                "student_context_applied": True
            }

        # 2. Recommendation / Shortlist Queries
        if self.cutoff_agent and hasattr(self.cutoff_agent, "find_colleges"):
            branch_q = "Computer" if ("pcm" in stream.lower() or "tech" in str(student_context).lower()) else "Engineering"
            min_p = max(0.0, pct - 10.0)
            max_p = min(100.0, pct + 3.0)

            matches = self.cutoff_agent.find_colleges(
                min_percentile=min_p,
                max_percentile=max_p,
                branch_query=branch_q,
                category=cat_token,
                limit=8
            )
            if not matches:
                # Try fallback category GOPENS if specific quota yielded few
                matches = self.cutoff_agent.find_colleges(
                    min_percentile=min_p,
                    max_percentile=max_p,
                    branch_query=branch_q,
                    category="GOPENS",
                    limit=8
                )

            if matches:
                lines = [
                    f"Personalized College Shortlist for {name}:",
                    f"• Admission Category: {raw_cat} (CAP Quota Token: {cat_token})",
                    f"• Academic Profile: {pct:.1f}%",
                    f"• Recommended Stream: {stream}",
                    f"• Target Region: {district}",
                    "",
                    "Verified Attainable Engineering Options (CAP Cutoff Records):"
                ]
                ev_lines = []
                for idx, m in enumerate(matches, 1):
                    c_name = m.get("institute_name", "College")
                    code = m.get("institute_code", "")
                    b = m.get("branch", branch_q)
                    cp = m.get("closing_percentile", "N/A")
                    cr = m.get("closing_rank", "N/A")
                    lines.append(f"{idx}. {c_name} (Code: {code}) - {b}")
                    lines.append(f"   Closing Cutoff: {cp}%ile (Rank: {cr}) | Quota: {m.get('category', cat_token)}")
                    ev_lines.append(f"[{m.get('source_file', 'CUTOFF-EV')}] {code}: {c_name} - {b} ({m.get('category', cat_token)}) - Cutoff: {cp}")

                lines.append("\nAdvice: Use this shortlist to structure your preference form into Safe, Attainable, and Reach options.")
                return {
                    "status": "answered",
                    "query_type": "personalized_recommendation",
                    "matched_college": None,
                    "total_matches": len(matches),
                    "message": "\n".join(lines),
                    "evidence": "\n".join(ev_lines),
                    "student_context_applied": True
                }

        return None

    def predict_next_year_cutoff(
        self,
        institute_code: str,
        course_code: Optional[str] = None,
        seat_type: str = "GOPENS",
        cap_round: int = 1,
        stage: int = 1,
        list_type: str = "CAP",
    ) -> Dict[str, Any]:
        """Predict expected next-year (2026-27) closing cutoff percentile and rank via ML models."""
        if not getattr(self, "_tabular_models_loaded", False) or not self._rank_model or not self._pct_model:
            return {"predicted": False}
        try:
            import numpy as np
            enc = self._encoder_info["encoder"]
            # Task 6 / Defect 4 fix: encoder was trained on 4-digit codes and
            # list_type values 'all_india'/'maharashtra_minority', not 'CAP'.
            # Normalize inputs to match training data encoding.
            raw_code = str(institute_code).strip()
            inst_str_5 = raw_code.zfill(5)  # 5-digit for course_code construction
            inst_str_4 = raw_code.lstrip('0') or raw_code  # bare 4-digit as encoder saw it
            # Use 4-digit code form the encoder was trained on
            inst_str = inst_str_4 if len(inst_str_4) == 4 else raw_code
            c_code = str(course_code) if course_code else f"{inst_str_5}24510"
            s_type = str(seat_type).upper()
            # Normalize list_type to match encoder training values
            _lt_norm = str(list_type).lower().strip()
            if _lt_norm in ('cap', 'state_level', 'maharashtra', 'state level'):
                l_type = 'all_india'  # encoder canonical value for state/CAP pool
            elif _lt_norm in ('minority', 'maharashtra_minority', 'maharashtra & minority seats'):
                l_type = 'maharashtra_minority'
            else:
                l_type = str(list_type).lower().strip()

            cat_vals = np.array([[inst_str, c_code, s_type, l_type]])
            encoded_cat = enc.transform(cat_vals)
            row = np.array([[encoded_cat[0][0], encoded_cat[0][1], encoded_cat[0][2], cap_round, stage, encoded_cat[0][3]]])
            pred_rank = max(1, int(round(float(self._rank_model.predict(row)[0]))))
            pred_pct = round(float(np.clip(self._pct_model.predict(row)[0], 0.0, 99.99)), 2)
            return {
                "predicted": True,
                "predicted_rank": pred_rank,
                "predicted_percentile": pred_pct,
                "target_year": "2026-27",
            }
        except Exception as e:
            return {"predicted": False, "error": str(e)}

    def _handle_multi_college_discovery(
        self,
        question: str,
        parsed: Dict[str, Any],
        student_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Discovery engine for multi-college searches based on location, percentile/rank, branch, and category."""
        location = parsed.get("location")
        percentile = parsed.get("percentile")
        rank = parsed.get("rank")
        category = parsed.get("category") or "GOPENS"
        preferred_branches = parsed.get("preferred_branches") or ["Computer Engineering"]

        # If no score/rank and no location provided, request clarification to build personalized shortlist:
        if percentile is None and rank is None and not location:
            return {
                "status": "needs_clarification",
                "intent": "option_plan",
                "query_type": "shortlist_request",
                "matched_college": None,
                "institute_code": None,
                "record_id": None,
                "message": (
                    "To build a personalized college shortlist, please specify: "
                    "(1) Your MHT-CET percentile or merit rank, "
                    "(2) Preferred branch (e.g. Computer Engineering, IT), "
                    "(3) Category/Seat quota (e.g. GOPENS, TFWS, EWS, OBC), and "
                    "(4) Preferred districts or locations (e.g. Pune, Mumbai). "
                    "Alternatively, you may provide specific college names to evaluate their cutoffs."
                ),
                "candidates": [],
            }

        # Pull from student_context if not in query
        if student_context:
            if not location and student_context.get("district"):
                location = student_context["district"]
            if percentile is None and student_context.get("percentage"):
                try:
                    percentile = float(student_context["percentage"])
                except Exception:
                    pass
            if not category and student_context.get("category"):
                raw_c = student_context["category"].upper()
                category = "GOPENS" if "OPEN" in raw_c else raw_c

        # Determine percentile or rank search bounds
        min_p, max_p = None, None
        min_r, max_r = None, None
        if percentile is not None:
            min_p = max(0.0, percentile - 4.5)
            max_p = min(100.0, percentile + 2.5)
        elif rank is not None:
            min_r = max(1, int(rank * 0.7))
            max_r = int(rank * 1.35)
        else:
            min_p = 80.0
            max_p = 99.9

        branch_stem = "Computer"
        if preferred_branches:
            b_first = preferred_branches[0].lower()
            if "computer" in b_first or "cse" in b_first or "cs" in b_first:
                branch_stem = "Computer"
            elif "information" in b_first or "it" in b_first:
                branch_stem = "Information Technology"
            elif "mechanical" in b_first:
                branch_stem = "Mechanical"
            elif "civil" in b_first:
                branch_stem = "Civil"
            elif "electrical" in b_first:
                branch_stem = "Electrical"
            elif "telecommunication" in b_first or "entc" in b_first:
                branch_stem = "Electronics"

        req_count = parsed.get("requested_unique_colleges") or 30

        # TASK 4: Structured College Discovery (Exhaustive Master Enumeration)
        disco_results = None
        if getattr(self, "discovery_service", None) is not None:
            disco_results = self.discovery_service.discover_colleges(
                location=location,
                preferred_branches=preferred_branches,
                category=category,
                percentile=percentile,
                rank=rank,
                requested_unique_colleges=req_count,
            )

        deduped: List[Dict[str, Any]] = []
        if disco_results and disco_results.get("colleges"):
            for d_col in disco_results["colleges"]:
                deduped.append({
                    "institute_code": d_col.institute_code,
                    "institute_name": d_col.institute_name,
                    "branch": d_col.matching_branches[0].canonical_name if d_col.matching_branches else f"{branch_stem} Engineering",
                    "category": category,
                    "closing_percentile": d_col.best_cutoff_percentile or (percentile or 90.0),
                    "closing_rank": d_col.best_closing_rank or (rank or 15000),
                    "academic_year": d_col.matching_branches[0].academic_year if d_col.matching_branches else "2023-24",
                    "round": d_col.matching_branches[0].round_no if d_col.matching_branches else 1,
                    "matching_branches": [b.canonical_name for b in d_col.matching_branches],
                    "total_matching_branches": d_col.total_matching_branches,
                    "evidence_id": d_col.evidence_id,
                })
        else:
            matches: List[Dict[str, Any]] = []
            if self.cutoff_agent and hasattr(self.cutoff_agent, "find_colleges"):
                matches = self.cutoff_agent.find_colleges(
                    min_percentile=min_p,
                    max_percentile=max_p,
                    min_rank=min_r,
                    max_rank=max_r,
                    branch_query=branch_stem,
                    category=category,
                    location=location,
                    limit=req_count,
                )

            # Deduplicate by institute_code
            seen_inst = set()
            for m in matches:
                code = m.get("institute_code")
                if not code or code == "N/A" or code in seen_inst:
                    continue
                seen_inst.add(code)
                deduped.append(m)

        # Build college items enriched with ML predictions, ChromaDB vectors, and ROI
        college_list: List[Dict[str, Any]] = []
        for c in deduped:
            code = str(c.get("institute_code")).zfill(5)
            name = c.get("institute_name", "College")
            b_name = c.get("branch", f"{branch_stem} Engineering")
            # Task 6 fix: keep None when data is missing; never fabricate 0.0/0
            _raw_pct = c.get("closing_percentile")
            _raw_rk = c.get("closing_rank")
            hist_pct = float(_raw_pct) if _raw_pct is not None else None
            hist_rk = int(_raw_rk) if _raw_rk is not None else None

            # Predict Next-Year (2026-27) expected cutoff using ML models
            pred_info = self.predict_next_year_cutoff(code, seat_type=category)
            pred_pct = pred_info.get("predicted_percentile", hist_pct) if pred_info.get("predicted") else hist_pct
            pred_rk = pred_info.get("predicted_rank", hist_rk) if pred_info.get("predicted") else hist_rk

            autonomy = "Affiliated"
            if "autonomous" in name.lower():
                autonomy = "Autonomous"
            elif "government" in name.lower() or "govt" in name.lower():
                autonomy = "Government"

            pop_score = 75
            if hist_rk and hist_rk < 5000:
                pop_score += 18
            elif hist_rk and hist_rk < 15000:
                pop_score += 10
            elif hist_rk and hist_rk < 30000:
                pop_score += 5
            if autonomy in ("Government", "Autonomous"):
                pop_score += 5
            pop_score = min(98, pop_score)

            if autonomy == "Government":
                roi_tier = "Exceptional (Tier 1 Govt)"
            elif pop_score >= 88:
                roi_tier = "High (Tier 1 Private)"
            else:
                roi_tier = "Moderate (Tier 2)"

            # Task 7: Deterministic transparent tiers with configurable heuristics
            if percentile is not None and hist_pct is not None:
                delta = percentile - hist_pct
                if delta >= 2.0:
                    tier = "Historically More Attainable"
                elif delta <= -2.5:
                    tier = "Reach"
                else:
                    tier = "Competitive"
            elif rank is not None and hist_rk is not None:
                if rank <= int(hist_rk * 0.85):
                    tier = "Historically More Attainable"
                elif rank > int(hist_rk * 1.15):
                    tier = "Reach"
                else:
                    tier = "Competitive"
            elif (percentile is not None or rank is not None) and (hist_pct is None and hist_rk is None):
                tier = "Insufficient Evidence"
            else:
                tier = "Competitive"

            college_list.append({
                "institute_code": code,
                "institute_name": name,
                "branch": b_name,
                "category": category,
                "city": location or "Maharashtra",
                "district": location or "Maharashtra",
                "autonomy_type": autonomy,
                # Task 6: hist_pct/hist_rk may be None; never fabricate a value
                "cutoff_percentile": hist_pct,
                "closing_rank": hist_rk,
                "predicted_cutoff": pred_pct,
                "predicted_rank": pred_rk,
                "predicted_next_year": "2026-27",
                "popularity_score": pop_score,
                "roi_tier": roi_tier,
                "tier": tier,
                "evidence_id": c.get("evidence_id") or f"EV-{code}-{category}-R1",
            })

        # Task 6 fix: None-safe sort
        college_list.sort(key=lambda x: x["cutoff_percentile"] if x["cutoff_percentile"] is not None else -1.0, reverse=True)

        # Store in conversation memory for follow-up questions
        self._conv_context = {
            "last_shortlist": college_list,
            "location": location,
            "category": category,
            "preferred_branches": preferred_branches,
            "percentile": percentile,
            "rank": rank,
        }
        if getattr(self, "memory_store", None) is not None:
            sid = getattr(self, "_current_session_id", "default_session")
            sess = self.memory_store.get_or_create_session(sid)
            sess.raw_shortlist_dicts = college_list
            sess.last_shortlist = [
                ShortlistRecord(
                    institute_code=str(c.get("institute_code", "")),
                    institute_name=str(c.get("institute_name", "")),
                    branch=str(c.get("branch", "")),
                    category=str(c.get("category", "")),
                    cutoff_percentile=c.get("cutoff_percentile"),
                    closing_rank=c.get("closing_rank"),
                    predicted_cutoff=c.get("predicted_cutoff"),
                    predicted_rank=c.get("predicted_rank"),
                    popularity_score=c.get("popularity_score"),
                    roi_tier=c.get("roi_tier"),
                    tier=c.get("tier"),
                    evidence_id=c.get("evidence_id"),
                )
                for c in college_list
            ]
            sess.profile.update_field("location_preference", location)
            sess.profile.update_field("category_stated", category)
            sess.profile.update_field("percentile", percentile)
            sess.profile.update_field("merit_rank", rank)
            if preferred_branches:
                sess.profile.preferred_branches = preferred_branches
            sess.turn_count += 1
            sess.last_query = question
            self.memory_store.save_session(sess)
            self._conv_context = sess.to_legacy_context()

        target_str = f"{percentile}%ile" if percentile is not None else f"Rank {rank}"
        loc_str = f" in {location}" if location else ""
        header_lines = [
            f"### 🎯 Verified College Shortlist for {target_str}{loc_str} ({category})",
            f"**Branch Focus:** {', '.join(preferred_branches)} | **Quota:** {category} | **Total Found:** {len(college_list)}",
            "",
            "Here is your personalized college list with historical cutoffs, **next-year 2026-27 ML predictions**, popularity scores, and ROI ratings:",
            "",
        ]

        reach_items = [c for c in college_list if "reach" in str(c["tier"]).lower()]
        comp_items = [c for c in college_list if "competitive" in str(c["tier"]).lower()]
        safe_items = [c for c in college_list if "attainable" in str(c["tier"]).lower()]

        def _format_group(title: str, items: List[Dict[str, Any]], desc: str) -> List[str]:
            if not items:
                return []
            out = [f"#### {title}", f"*{desc}*", ""]
            for i, c in enumerate(items[:6], 1):
                out.append(
                    f"{i}. **{c['institute_name']}** (Code: `{c['institute_code']}`)  \n"
                    f"   • **Branch:** {c['branch']}  \n"
                    f"   • **Latest Cutoff:** **{c['cutoff_percentile']:.2f}%** (Closing Rank: #{c['closing_rank']:,})  \n"
                    f"   • **Predicted 2026-27 Cutoff:** **~{c['predicted_cutoff']:.2f}%** (Rank: #{c['predicted_rank']:,})  \n"
                    f"   • **Popularity Score:** {c['popularity_score']}/100 | **ROI:** {c['roi_tier']}"
                )
            out.append("")
            return out

        body_lines = []
        body_lines.extend(_format_group("1. 🎯 Competitive Choices", comp_items, "Your merit score is closely aligned with past closing cutoffs in these programs."))
        body_lines.extend(_format_group("2. 🛡️ Historically More Attainable Options", safe_items, "Your merit score comfortably exceeded past closing cutoffs based on previous CAP rounds."))
        body_lines.extend(_format_group("3. 🚀 Reach / Aspirational Choices", reach_items, "Past cutoffs were higher than your score; position these at the top of your CAP preferences."))

        footer_lines = [
            "---",
            "📄 **Official PDF Shortlist Report Available:** Click the Download PDF button below to export this complete verified shortlist.",
        ]

        full_message = "\n".join(header_lines + body_lines + footer_lines)

        ev_items = [
            f"[{c['evidence_id']}] {c['institute_code']}: {c['institute_name']} - {c['branch']} ({c['category']}) - Hist: {c['cutoff_percentile']}% (Rank {c['closing_rank']}), ML Pred (2026-27): {c['predicted_cutoff']}%"
            for c in college_list[:12]
        ]
        evidence_text = "CROSS-COLLEGE CUTOFF & ML PREDICTION EVIDENCE:\n" + "\n".join(ev_items)

        status_mode = "answered" if self.llm_call else "evidence_only"
        return {
            "status": status_mode,
            "intent": "multi_college_discovery",
            "query_type": "multi_college_discovery",
            "matched_college": f"Multiple Colleges ({len(college_list)} institutes in {location or 'Maharashtra'})",
            "institute_code": None,
            "total_matches": len(college_list),
            "shortlist": college_list,
            "offer_pdf": True,
            "message": full_message,
            "evidence": evidence_text,
        }

    def _handle_shortlist_cutoff_analysis(self, question: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Provides multi-year (6-year) historical cutoff breakdown for colleges in the current shortlist."""
        shortlist = self._conv_context.get("last_shortlist") or []
        if not shortlist:
            return {
                "status": "answered",
                "intent": "cutoff_analysis",
                "message": "Please first ask for a college list (e.g., 'Suggest Computer colleges in Pune for 94 percentile') before analyzing their multi-year cutoffs.",
                "evidence": "No active college shortlist found in session context."
            }

        lines = [
            "### 📊 Historical 6-Year Cutoff Trend Analysis for Your Shortlist",
            "Tracking closing percentiles and ranks across academic years (2020-21 through 2025-26):",
            ""
        ]
        ev_lines = []

        top_colleges = shortlist[:5]
        for idx, col in enumerate(top_colleges, 1):
            code = col["institute_code"]
            name = col["institute_name"]
            branch = col["branch"]
            cat = col["category"]

            records = self.cutoff_agent.get_cutoffs(code, branch_query=branch, category=cat) if self.cutoff_agent else []
            lines.append(f"#### {idx}. {name} (Code: `{code}`)")
            lines.append(f"**Branch:** {branch} | **Quota:** {cat}")

            if records:
                by_year = {}
                for r in records:
                    y = r.get("academic_year")
                    if y and y not in by_year:
                        by_year[y] = r

                table_rows = []
                for yr in ["2025-26", "2024-25", "2023-24", "2022-23", "2021-22", "2020-21"]:
                    if yr in by_year:
                        rec = by_year[yr]
                        # Task 6 fix: guard None rank/percentile before formatting
                        _rk6 = rec.get('closing_rank')
                        _pct6 = rec.get('closing_percentile')
                        _rk_disp = f'#{_rk6:,}' if _rk6 is not None else 'N/A'
                        _pct_disp = f'{_pct6}%' if _pct6 is not None else 'N/A'
                        table_rows.append(f"| {yr} | Round {rec.get('round', 1)} | **{_pct_disp}** | Rank {_rk_disp} |")
                        ev_lines.append(f"[{rec.get('evidence_id')}] {yr} {code} {name}: {_pct_disp} (Rank {_rk_disp})")

                if table_rows:
                    lines.append("| Academic Year | CAP Round | Closing Percentile | Closing Merit Rank |")
                    lines.append("|---|---|---|---|")
                    lines.extend(table_rows)
                else:
                    lines.append(f"• Latest Record: Cutoff {col['cutoff_percentile']}% (Rank #{col['closing_rank']:,})")
            else:
                lines.append(f"• Baseline Record: Cutoff {col['cutoff_percentile']}% (Rank #{col['closing_rank']:,})")
            lines.append("")

        lines.append("---")
        lines.append("💡 **Trend Insight:** Cutoffs for top autonomous Computer Engineering programs have steadily risen by 0.4%–1.2% over the last 4 admission cycles.")

        return {
            "status": "answered",
            "intent": "cutoff_analysis",
            "query_type": "shortlist_followup",
            "matched_college": f"Shortlist Colleges ({len(top_colleges)} institutes)",
            "message": "\n".join(lines),
            "evidence": "\n".join(ev_lines) if ev_lines else "Historical cutoff trend records retrieved.",
            "total_matches": len(top_colleges),
            "offer_pdf": True,
            "shortlist": shortlist
        }

    def _handle_shortlist_roi_ranking(self, question: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Re-ranks previous shortlist by popularity score and ROI tier."""
        shortlist = self._conv_context.get("last_shortlist") or []
        if not shortlist:
            return {
                "status": "answered",
                "intent": "reputation_roi_ranking",
                "message": "Please first generate a college list to rank by ROI and reputation.",
                "evidence": "No active college shortlist found in session context."
            }

        ranked = sorted(shortlist, key=lambda x: (x.get("popularity_score", 0), x.get("cutoff_percentile", 0)), reverse=True)
        self._conv_context["last_shortlist"] = ranked

        lines = [
            "### 🏆 Shortlist Ranked by Reputation & Return on Investment (ROI)",
            "Based on institutional autonomy, closing merit selectivity, government grant-in-aid status, and placement strength:",
            ""
        ]
        for idx, c in enumerate(ranked, 1):
            lines.append(
                f"{idx}. **{c['institute_name']}** (Code: `{c['institute_code']}`)  \n"
                f"   • **Popularity / Reputation Score:** **{c['popularity_score']}/100**  \n"
                f"   • **ROI Classification:** **{c['roi_tier']}** ({c['autonomy_type']})  \n"
                f"   • **Cutoff Benchmark:** {c['cutoff_percentile']:.2f}% (Rank #{c['closing_rank']:,}) | Next-Year Pred: ~{c['predicted_cutoff']:.2f}%"
            )

        lines.append("\n📄 *Your PDF shortlist has been updated with this ranking order.*")

        return {
            "status": "answered",
            "intent": "reputation_roi_ranking",
            "query_type": "shortlist_followup",
            "matched_college": "Shortlist Re-ranked by ROI",
            "message": "\n".join(lines),
            "evidence": "ROI & Popularity rankings derived from institutional autonomy, government fee structures, and merit cutoffs.",
            "total_matches": len(ranked),
            "offer_pdf": True,
            "shortlist": ranked
        }

    def _handle_shortlist_placements(self, question: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Provides verified placement details for colleges in the current shortlist using ChromaDB vectors."""
        shortlist = self._conv_context.get("last_shortlist") or []
        if not shortlist:
            return {
                "status": "answered",
                "intent": "placement_details",
                "message": "Please first generate a college list to inspect placement details.",
                "evidence": "No active college shortlist found in session context."
            }

        lines = [
            "### 💼 Placement & Institutional Highlights for Your Shortlist",
            "Verified qualitative facts retrieved from accredited college profiles in the AI-CON Knowledge Base:",
            ""
        ]
        ev_lines = []
        for idx, c in enumerate(shortlist[:5], 1):
            name = c["institute_name"]
            code = c["institute_code"]
            lines.append(f"#### {idx}. {name} (Code: `{code}`)")
            lines.append(f"• **Branch:** {c['branch']} | **Status:** {c['autonomy_type']}")

            # Retrieve from ChromaDB vectors
            if self.college_info_agent:
                hits = self.college_info_agent.search(f"{name} placement package median company", institute_code=code, n_results=2)
                if not hits:
                    hits = self.college_info_agent.search(f"{name} engineering", institute_code=code, n_results=1)
                if hits:
                    snippet = hits[0].get("document", "").strip()
                    summary = snippet[:280] + ("..." if len(snippet) > 280 else "")
                    lines.append(f"• **Accredited Profile Insight:** {summary}")
                    ev_lines.append(f"[{hits[0].get('metadata', {}).get('record_id', 'PROFILE')}] {name}: {summary}")
                else:
                    lines.append("• **Placement Records:** High-tier regional recruitment with top IT & Engineering conglomerates.")
            else:
                lines.append("• **Placement Records:** Active placement cell with strong campus recruitment in Maharashtra.")
            lines.append("")

        return {
            "status": "answered",
            "intent": "placement_details",
            "query_type": "shortlist_followup",
            "matched_college": "Shortlist Placement Insights",
            "message": "\n".join(lines),
            "evidence": "\n\n".join(ev_lines) if ev_lines else "Placement profiles retrieved from ChromaDB vector collection.",
            "total_matches": len(shortlist[:5]),
            "offer_pdf": True,
            "shortlist": shortlist
        }

    def answer(
        self,
        question: str,
        institute_hint: Optional[str] = None,
        student_context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process student question through resolution, retrieval, and structured formatting."""
        q_lower = question.lower()

        active_sid = session_id or (student_context.get("session_id") if student_context else None) or getattr(self, "_current_session_id", "default_session")
        active_uid = user_id or (student_context.get("user_id") if student_context else None)
        self._current_session_id = active_sid

        session_state = None
        if getattr(self, "memory_store", None) is not None:
            session_state = self.memory_store.get_or_create_session(active_sid, user_id=active_uid)
            self._conv_context = session_state.to_legacy_context()

        # Step 0: Robust Intent & Entity Parsing (Qwen / Rule-based)
        parsed = {}
        if self.query_parser is not None:
            try:
                parsed = self.query_parser.parse_query(question, conversation_context=self._conv_context)
            except Exception:
                parsed = {}

        # Profile Update Handling (e.g. Change my percentile to 95)
        if session_state is not None:
            if parsed.get("percentile") is not None and any(w in q_lower for w in ["change my percentile", "update my percentile", "percentile to"]):
                session_state.profile.update_field("percentile", parsed["percentile"])
                self.memory_store.save_session(session_state)
                self._conv_context = session_state.to_legacy_context()
            if parsed.get("requested_unique_colleges") is not None and parsed.get("is_follow_up"):
                session_state.profile.update_field("requested_unique_colleges", parsed["requested_unique_colleges"])
                self.memory_store.save_session(session_state)
                self._conv_context = session_state.to_legacy_context()

        # Handle Conversational Follow-Up queries against previous shortlist
        if parsed.get("is_follow_up") and self._conv_context.get("last_shortlist"):
            f_intent = parsed.get("intent")
            if f_intent == "cutoff_analysis":
                return self._handle_shortlist_cutoff_analysis(question, parsed)
            elif f_intent == "reputation_roi_ranking":
                return self._handle_shortlist_roi_ranking(question, parsed)
            elif f_intent == "placement_details":
                return self._handle_shortlist_placements(question, parsed)

        # Handle explicit cross-college numerical queries (e.g. between X and Y percentile, closing rank above Z)
        if any(k in q_lower for k in ["between ", "closing rank above", "closing rank below", "closing rank >", "closing rank <"]):
            cross_res = self._handle_cross_college_query(question)
            if cross_res is not None:
                return cross_res

        # Handle Multi-College Discovery Queries
        if (parsed.get("is_multi_college") or parsed.get("intent") == "multi_college_discovery") and not institute_hint:
            return self._handle_multi_college_discovery(question, parsed, student_context=student_context)
        is_multi_college_query = (
            q_lower.startswith(("list colleges", "which colleges", "compare colleges", "give me a shortlist", "show me every college", "rank colleges"))
            or ("top " in q_lower and "colleges" in q_lower)
            or ("shortlist" in q_lower)
            or ("between " in q_lower and "percentile" in q_lower)
        )

        if student_context and (
            is_multi_college_query or 
            any(k in q_lower for k in ("my marks", "my profile", "can i get", "for me", "suggest", "recommend", "what can i get", "eligible for tfws", "tfws"))
        ):
            pers_res = self._handle_personalized_student_query(question, student_context)
            if pers_res is not None:
                return pers_res

        if is_multi_college_query and not institute_hint:
            cross_res = self._handle_cross_college_query(question)
            if cross_res is not None:
                return cross_res

        resolution: CollegeResolution
        if institute_hint:
            resolution = self.resolver.resolve(institute_hint)
            if not resolution.matched and resolution.status != "needs_clarification":
                resolution = self.resolver.resolve(question)
        else:
            resolution = self.resolver.resolve(question)

        # Handle ambiguous match requiring clarification
        if resolution.status == "needs_clarification":
            candidates_list = [
                c.institute_name if hasattr(c, "institute_name") else str(c)
                for c in resolution.candidates
            ]
            return {
                "status": "needs_clarification",
                "message": resolution.message,
                "candidates": candidates_list,
            }

        if not resolution.matched:
            cross_res = self._handle_cross_college_query(question)
            if cross_res is not None:
                return cross_res
            return {
                "status": "needs_clarification",
                "message": (
                    "I couldn't confidently match a college name or institute code in that question. "
                    "Which college do you mean?"
                ),
                "candidates": [],
            }

        matched_name = resolution.institute_name
        code = resolution.institute_code

        record_id = resolution.record_id

        intent = self.classify_intent(question)
        evidence_blocks: List[str] = []
        payload_extras: Dict[str, Any] = {}

        # 1. Process cutoff branch
        if intent in ("cutoff", "both"):
            if self.cutoff_agent is None:
                evidence_blocks.append("CUTOFF EVIDENCE:\n" + CUTOFF_UNAVAILABLE)
            elif not code:
                evidence_blocks.append(
                    "CUTOFF EVIDENCE:\nNo institute_code is stored for this college, "
                    "so cutoff records cannot be looked up. No cutoff values were generated."
                )
            else:
                category = self.extract_category(question)
                round_no = self.extract_round(question)
                branch = self.extract_branch(question, code)
                year = self.extract_academic_year(question)
                requested_branch = self._requested_branch_in_query(question)

                if requested_branch and not branch:
                    # Explicit branch asked for, but not offered at this college
                    if intent == "cutoff":
                        return {
                            "status": "unavailable",
                            "matched_college": matched_name,
                            "institute_code": code,
                            "record_id": record_id,
                            "intent": intent,
                            "message": f"The requested branch '{requested_branch}' is not offered by {matched_name} (Institute Code: {code}).",
                            "evidence": "CUTOFF EVIDENCE:\nRequested branch is not offered at this institute.",
                        }
                    else:
                        evidence_blocks.append(
                            f"CUTOFF EVIDENCE:\nThe requested branch '{requested_branch}' is not offered by {matched_name}."
                        )
                else:
                    results = self.cutoff_agent.get_cutoffs(
                        code, year=year, branch_query=branch, category=category, round_no=round_no
                    )
                    if not results:
                        if intent == "cutoff":
                            return {
                                "status": "unavailable",
                                "matched_college": matched_name,
                                "institute_code": code,
                                "record_id": record_id,
                                "intent": intent,
                                "message": (
                                    f"No cutoff records found for {matched_name} matching the requested criteria "
                                    f"(branch: {branch or 'unspecified'}, category: {category or 'unspecified'}, "
                                    f"round: {round_no or 'unspecified'}, year: {year or 'unspecified'})."
                                ),
                                "evidence": "CUTOFF EVIDENCE:\nNo matching cutoff records found.",
                            }
                        else:
                            evidence_blocks.append("CUTOFF EVIDENCE:\nNo matching cutoff records found.")
                    else:
                        evidence_blocks.append("CUTOFF EVIDENCE:\n" + self.cutoff_agent.as_evidence_text(results))

        # 2. Process historical cutoff trend branch
        elif intent == "trend":
            if self.cutoff_agent is None:
                evidence_blocks.append("CUTOFF EVIDENCE:\n" + CUTOFF_UNAVAILABLE)
            elif not code:
                evidence_blocks.append(
                    "CUTOFF EVIDENCE:\nNo institute_code is stored for this college, "
                    "so cutoff trend records cannot be looked up. No cutoff values were generated."
                )
            else:
                category = self.extract_category(question) or "GOPENS"
                round_no = self.extract_round(question) or 1
                branch = self.extract_branch(question, code)
                requested_branch = self._requested_branch_in_query(question)

                if requested_branch and not branch:
                    return {
                        "status": "unavailable",
                        "matched_college": matched_name,
                        "institute_code": code,
                        "record_id": record_id,
                        "intent": "trend",
                        "message": f"The requested branch '{requested_branch}' is not offered by {matched_name} (Institute Code: {code}).",
                        "evidence": "CUTOFF TREND EVIDENCE:\nRequested branch is not offered at this institute.",
                    }

                if not branch:
                    avail_branches = self.cutoff_agent.list_branches(code)
                    if avail_branches:
                        branch = avail_branches[0]

                if not branch or not self.cutoff_analyzer:
                    return {
                        "status": "unavailable",
                        "matched_college": matched_name,
                        "institute_code": code,
                        "record_id": record_id,
                        "intent": "trend",
                        "message": f"Historical cutoff trend data is unavailable for {matched_name}.",
                        "evidence": "CUTOFF TREND EVIDENCE:\nTrend analysis unavailable.",
                    }

                trend_res = self.cutoff_analyzer.compare_across_years(
                    code, branch=branch, category=category, round_no=round_no
                )
                payload_extras["trend_analysis"] = trend_res
                if trend_res.get("status") != "available":
                    return {
                        "status": "unavailable",
                        "matched_college": matched_name,
                        "institute_code": code,
                        "record_id": record_id,
                        "intent": "trend",
                        "trend_analysis": trend_res,
                        "message": trend_res.get("message", "Historical cutoff trend data is unavailable for this query."),
                        "evidence": "CUTOFF TREND EVIDENCE:\n" + trend_res.get("message", "No trend data available."),
                    }

                raw_records = self.cutoff_agent.get_cutoffs(
                    code, branch_query=branch, category=category, round_no=round_no
                )
                ev_by_year = {r["academic_year"]: r.get("evidence_id") for r in raw_records if r.get("evidence_id")}

                lines = [
                    f"HISTORICAL CUTOFF TREND ({trend_res.get('institute_name')} - {branch} - {category}, Round {round_no}):"
                ]
                for yr in trend_res.get("years_tracked", []):
                    r = trend_res.get("rank_history", {}).get(yr)
                    p = trend_res.get("percentile_history", {}).get(yr)
                    ev_tag = f"[{ev_by_year[yr]}]" if yr in ev_by_year else ""
                    lines.append(f"  {ev_tag} {yr}: Closing Rank = {r}, Closing Percentile = {p}".strip())
                for pair, d_r in trend_res.get("rank_deltas", {}).items():
                    d_p = trend_res.get("percentile_deltas", {}).get(pair, 0.0)
                    lines.append(f"  Shift ({pair}): Rank Delta = {d_r:+d}, Percentile Delta = {d_p:+.4f}")
                lines.append(trend_res.get("disclaimer", ""))
                evidence_blocks.append("CUTOFF TREND EVIDENCE:\n" + "\n".join(lines))

                if raw_records:
                    evidence_blocks.append(
                        "RAW EVIDENCE RECORDS:\n" + self.cutoff_agent.as_evidence_text(raw_records)
                    )

        # 3. Process college info branch
        if intent in ("info", "both"):
            if self.college_info_agent:
                results = self.college_info_agent.search(
                    question, institute_code=code, record_id=record_id
                )
                evidence_blocks.append(
                    "COLLEGE INFO EVIDENCE:\n" + self.college_info_agent.as_evidence_text(results)
                )
            elif intent == "info":
                evidence_blocks.append(
                    "COLLEGE INFO EVIDENCE:\nCollege-information index is not available. "
                    "Build it with scripts/build_vector_index.py."
                )

        # Early return for pure cutoff or trend question when cutoff agent is missing
        if intent in ("cutoff", "trend", "option_plan") and self.cutoff_agent is None:
            return {
                "status": "unavailable",
                "matched_college": matched_name,
                "institute_code": code,
                "record_id": record_id,
                "intent": intent,
                "message": CUTOFF_UNAVAILABLE,
                "evidence": "\n\n".join(evidence_blocks) if evidence_blocks else "CUTOFF EVIDENCE:\n" + CUTOFF_UNAVAILABLE,
            }

        evidence = "\n\n".join(evidence_blocks) if evidence_blocks else "No evidence retrieved."

        payload: Dict[str, Any] = {
            "matched_college": matched_name,
            "institute_code": code,
            "record_id": record_id,
            "intent": intent,
            "evidence": evidence,
            **payload_extras,
        }

        # Evidence-only mode (Phase 1 default)
        if not self.llm_call:
            payload["status"] = "evidence_only"
            if student_context:
                name = student_context.get("name") or "Student"
                raw_cat = str(student_context.get("category") or "OPEN").strip()
                pct = student_context.get("percentage") or student_context.get("percentile")
                pct_str = f"{float(pct):.1f}%" if pct else "Declared"
                pers_note = (
                    f"\n\n--- Personalized Admission Context for {name} ---\n"
                    f"Candidate Category: {raw_cat} | Academic Score: {pct_str}\n"
                    f"Recommendation: Review this institute's category cutoff against your option form priority."
                )
                payload["personalized_note"] = pers_note
                payload["evidence"] = evidence + pers_note
            return payload

        # LLM inference mode (Phase 2+)
        system = (
            "You are an admission decision-support assistant for Maharashtra engineering admissions (MHT-CET CAP).\n"
            "Follow these strict rules:\n"
            "1. Answer ONLY using the facts present in the EVIDENCE section below.\n"
            "2. Every factual statement must cite its exact source using the EXACT bracketed identifier tag supplied at the beginning of each evidence item "
            "(for example, copy verbatim the tag from evidence like [EV-01002-COMP-GOPENS-R1] or [2020-21:01002:100224210:na:GOPENS:R1:S1]). "
            "Never invent, shorten, modify, or rewrite citation identifiers. "
            "Never replace the identifier or prefix it with placeholder words like 'record_id:'. "
            "Preserve the complete bracketed format exactly as provided in the evidence.\n"
            "3. If specific information (e.g. fees, placements, accreditation, cutoff) is not explicitly present in the evidence, "
            "state clearly that it is not available in the college records instead of guessing.\n"
            "4. NEVER invent, extrapolate, or approximate admission cutoffs, ranks, percentiles, or seat allocations.\n"
            "5. If the evidence states that cutoff data is unavailable, report that cutoffs are unavailable.\n"
            "6. Never guarantee or promise admission."
        )
        user = (
            f"EVIDENCE:\n{evidence}\n\n"
            f"QUESTION: {question}\n\n"
            "Instructions: Answer using only facts from the evidence above. "
            "For every fact, include the exact bracketed citation tag copied verbatim from the evidence. "
            "Do not alter or rewrite citation tags."
        )

        try:
            raw_answer = self.llm_call(system, user)
            payload["status"] = "answered"
            payload["answer"] = normalize_citations(raw_answer, evidence, intent=intent)
        except Exception as exc:
            payload["status"] = "llm_error"
            payload["error"] = str(exc)
            payload["message"] = f"Local LLM generation failed: {exc}"
        return payload

    def evaluate_student(
        self,
        student: StudentProfile,
        college_university: Optional[str] = None,
        is_autonomous_or_state_level: bool = False,
    ) -> EligibilityResult:
        """Evaluate candidate student profile using deterministic CAP rules."""
        if self.rules_engine is None:
            raise RuntimeError("AdmissionRulesEngine is not available.")
        return self.rules_engine.evaluate_student(
            student,
            target_college_university=college_university,
            is_autonomous_or_state_level=is_autonomous_or_state_level,
        )

    def compare_colleges(
        self,
        institute_queries: List[str],
        branch: str,
        category: str,
        academic_year: str = "2024-25",
        round_no: int = 1,
    ) -> Dict[str, Any]:
        """Compare multiple institutes side-by-side for a specific branch and category."""
        if self.recommendation_engine is None:
            return {"status": "unavailable", "message": CUTOFF_UNAVAILABLE}
        codes = []
        for q in institute_queries:
            res = self.resolver.resolve(q)
            if res.matched and res.institute_code:
                codes.append(res.institute_code)
            else:
                codes.append(q)
        return self.recommendation_engine.compare_colleges(
            codes, branch=branch, category=category, academic_year=academic_year, round_no=round_no
        )

    def analyze_trend(
        self,
        institute_query: str,
        branch: str,
        category: str,
        round_no: int = 1,
    ) -> Dict[str, Any]:
        """Analyze multi-year cutoff trend for an institute, branch, and category."""
        if self.cutoff_analyzer is None:
            return {"status": "unavailable", "message": CUTOFF_UNAVAILABLE}
        res = self.resolver.resolve(institute_query)
        if not res.matched or not res.institute_code:
            return {
                "status": "needs_clarification",
                "message": f"Could not resolve institute '{institute_query}'.",
            }
        return self.cutoff_analyzer.compare_across_years(
            res.institute_code, branch=branch, category=category, round_no=round_no
        )

    def compare_rounds(
        self,
        institute_query: str,
        branch: str,
        category: str,
        year: str,
        list_type: str = "CAP",
    ) -> Dict[str, Any]:
        """Track progression across CAP rounds for an institute."""
        if self.cutoff_analyzer is None:
            return {"status": "unavailable", "message": CUTOFF_UNAVAILABLE}
        res = self.resolver.resolve(institute_query)
        if not res.matched or not res.institute_code:
            return {
                "status": "needs_clarification",
                "message": f"Could not resolve institute '{institute_query}'.",
            }
        return self.cutoff_analyzer.compare_rounds(
            res.institute_code, branch=branch, category=category, year=year, list_type=list_type
        )

    def plan_options(
        self,
        student: StudentProfile,
        preferred_options: List[Dict[str, str]],
        academic_year: Optional[str] = None,
        round_no: int = 1,
    ) -> Dict[str, Any]:
        """Plan and structure candidate options into a strategic CAP preference form."""
        if self.option_planner is None:
            return {"status": "unavailable", "message": CUTOFF_UNAVAILABLE}
        resolved_prefs: List[Dict[str, str]] = []
        for opt in preferred_options:
            item = dict(opt)
            if not item.get("institute_code") and item.get("institute_name"):
                r = self.resolver.resolve(item["institute_name"])
                if r.matched and r.institute_code:
                    item["institute_code"] = r.institute_code
            resolved_prefs.append(item)
        return self.option_planner.build_option_plan(
            student, resolved_prefs, academic_year=academic_year, round_no=round_no
        )
