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
        # 1. Search for discipline phrases preceding engineering/technology/tech/branch
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

        # 2. Fallback: check for standalone discipline keywords in the query
        q_lower = question.lower()
        for disc, canonical_name in sorted(KNOWN_DISCIPLINES.items(), key=lambda x: len(x[0]), reverse=True):
            pattern = rf"\b{re.escape(disc)}\b"
            if re.search(pattern, q_lower):
                return canonical_name

        return None

    def answer(self, question: str, institute_hint: Optional[str] = None) -> Dict[str, Any]:
        """Process student question through resolution, retrieval, and structured formatting."""
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
