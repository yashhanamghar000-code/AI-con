"""
College Name & Code Resolution Module (Phase 1)
-----------------------------------------------
Provides deterministic, reliable resolution of user college references to:
  - institute_code (when available)
  - record_id
  - canonical institute_name

Resolution Strategy:
1. Exact Institute Code Match: 4-5 digit codes (e.g. '01002', '3208').
2. Exact Record ID Match: 'MHHEI_XXXXX'.
3. Exact Normalized Name Match: case-insensitive, punctuation-stripped.
4. Full College Name Contained in Query: longer, more specific names preferred.
5. Subphrase & Shared Prefix Match: If multiple colleges share the same
   root/prefix (e.g. 'Government College of Engineering' without city, or
   'Ram Meghe'), the resolver identifies the genuine ambiguity and returns
   status='needs_clarification' with the list of candidate colleges.
6. Conservative Fuzzy Match: high similarity cutoff (>= 0.75) to prevent silent misdirection.

Kept strictly separate from LLM generation and vector retrieval.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


STOP_WORDS: Set[str] = {
    "what", "is", "was", "were", "are", "the", "of", "in", "at", "for", "and", "about",
    "tell", "me", "cutoff", "cutoffs", "fees", "fee", "affiliation", "affiliated",
    "location", "district", "city", "round", "closing", "rank", "percentile",
    "please", "can", "you", "details", "info", "information",
}


def normalize_text(text: str) -> str:
    """Normalize text by lowercasing and stripping punctuation and trailing artifacts."""
    if not text:
        return ""
    # Strip punctuation characters
    clean = re.sub(r"[^\w\s]", " ", text.lower())
    # Collapse consecutive whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def extract_significant_tokens(text: str) -> Set[str]:
    """Extract tokens of length > 2 excluding conversational stop words."""
    norm = normalize_text(text)
    tokens = set()
    for tok in norm.split():
        if len(tok) > 2 and tok not in STOP_WORDS:
            tokens.add(tok)
    return tokens


def extract_query_candidate_phrases(query: str) -> List[str]:
    """Extract candidate college search phrases by stripping question prefixes and suffixes."""
    norm = normalize_text(query)
    prefixes = [
        "what was the cutoff for ",
        "what is the cutoff for ",
        "what were the cutoffs for ",
        "what are the cutoffs for ",
        "what was the closing rank for ",
        "what is the closing rank for ",
        "what is the affiliation of ",
        "what are the affiliations of ",
        "what is the fee of ",
        "what are the fees of ",
        "what are the fees for ",
        "what is the address of ",
        "what is the location of ",
        "can you tell me the address of ",
        "can you tell me about ",
        "tell me the cutoff of ",
        "tell me about ",
        "cutoff for ",
        "cutoffs for ",
        "information about ",
        "info about ",
        "details of ",
        "about ",
    ]
    cleaned = norm
    for p in prefixes:
        if cleaned.startswith(p):
            cleaned = cleaned[len(p):].strip()
            break

    suffixes = [
        " please",
        " in round 1", " in round 2", " in round 3", " in round 4",
        " for round 1", " for round 2", " for round 3",
        " round 1", " round 2", " round 3",
    ]
    for s in suffixes:
        if cleaned.endswith(s):
            cleaned = cleaned[:-len(s)].strip()

    phrases = []
    if cleaned and len(cleaned) >= 4:
        phrases.append(cleaned)
    if norm != cleaned and norm not in phrases:
        phrases.append(norm)
    return phrases


@dataclass
class ResolutionCandidate:
    institute_name: str
    institute_code: Optional[str]
    record_id: Optional[str]
    score: float
    match_type: str  # 'code', 'record_id', 'exact_name', 'contained', 'fuzzy', 'phrase_ambiguous'


@dataclass
class CollegeResolution:
    matched: bool
    status: str  # 'resolved', 'needs_clarification', 'not_found'
    institute_name: Optional[str] = None
    institute_code: Optional[str] = None
    record_id: Optional[str] = None
    confidence: float = 0.0
    match_type: str = "none"
    candidates: List[ResolutionCandidate] = field(default_factory=list)
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "status": self.status,
            "institute_name": self.institute_name,
            "institute_code": self.institute_code,
            "record_id": self.record_id,
            "confidence": self.confidence,
            "match_type": self.match_type,
            "message": self.message,
            "candidates": [
                {
                    "name": c.institute_name,
                    "code": c.institute_code,
                    "record_id": c.record_id,
                    "score": c.score,
                    "match_type": c.match_type,
                }
                for c in self.candidates
            ],
        }


class CollegeResolver:
    """Resolves college queries to verified college records."""

    def __init__(self):
        # canonical_name -> {"institute_code": str, "record_id": str}
        self._name_index: Dict[str, Dict[str, Optional[str]]] = {}
        # normalized_name -> canonical_name
        self._norm_to_canonical: Dict[str, str] = {}
        # code (str) -> canonical_name
        self._code_to_canonical: Dict[str, str] = {}
        # record_id (str) -> canonical_name
        self._record_id_to_canonical: Dict[str, str] = {}

    def register(
        self,
        institute_name: str,
        institute_code: Optional[str] = None,
        record_id: Optional[str] = None,
    ) -> None:
        """Register a college name and its identifiers."""
        if not institute_name:
            return
        name = institute_name.strip()
        code_str = str(institute_code).strip() if institute_code is not None else None
        rec_id_str = str(record_id).strip() if record_id is not None else None

        entry = self._name_index.setdefault(name, {"institute_code": None, "record_id": None})
        if code_str:
            entry["institute_code"] = code_str
            self._code_to_canonical[code_str] = name
            # Also register without leading zero if 5 digits starting with 0
            if len(code_str) == 5 and code_str.startswith("0"):
                self._code_to_canonical[code_str[1:]] = name
        if rec_id_str:
            entry["record_id"] = rec_id_str
            self._record_id_to_canonical[rec_id_str] = name

        norm_name = normalize_text(name)
        if norm_name:
            self._norm_to_canonical[norm_name] = name

    def register_from_dict(self, college_dict: Dict[str, Dict[str, Optional[str]]]) -> None:
        """Register multiple entries from a dictionary mapping name to attributes."""
        for name, attrs in college_dict.items():
            self.register(
                institute_name=name,
                institute_code=attrs.get("institute_code"),
                record_id=attrs.get("record_id"),
            )

    def size(self) -> int:
        return len(self._name_index)

    def resolve(self, query: str, fuzzy_cutoff: float = 0.75) -> CollegeResolution:
        """Resolve a user query to a college record.

        Checks:
        1. Explicit record_id token in query.
        2. Explicit institute_code token in query.
        3. Exact normalized full-name match.
        4. Full college name contained within query.
        5. Specific subphrase/root match across colleges with ambiguity detection.
        6. Conservative fuzzy matching with gap analysis.
        """
        if not query or not self._name_index:
            return CollegeResolution(
                matched=False,
                status="not_found",
                message="No college database loaded or empty query.",
            )

        # 1. Check for explicit record_id (e.g. MHHEI_00001)
        rec_id_match = re.search(r"\b(MHHEI_\d{5})\b", query, re.I)
        if rec_id_match:
            rec_id = rec_id_match.group(1).upper()
            if rec_id in self._record_id_to_canonical:
                name = self._record_id_to_canonical[rec_id]
                code = self._name_index[name].get("institute_code")
                return CollegeResolution(
                    matched=True,
                    status="resolved",
                    institute_name=name,
                    institute_code=code,
                    record_id=rec_id,
                    confidence=1.0,
                    match_type="record_id",
                )

        # 2. Check for explicit institute_code (4 or 5 digits)
        code_candidates = re.findall(r"\b(\d{4,5})\b", query)
        for cand in code_candidates:
            cand_padded = cand.zfill(5) if len(cand) == 4 else cand
            if cand in self._code_to_canonical:
                name = self._code_to_canonical[cand]
                entry = self._name_index[name]
                return CollegeResolution(
                    matched=True,
                    status="resolved",
                    institute_name=name,
                    institute_code=entry.get("institute_code"),
                    record_id=entry.get("record_id"),
                    confidence=1.0,
                    match_type="code",
                )
            if cand_padded in self._code_to_canonical:
                name = self._code_to_canonical[cand_padded]
                entry = self._name_index[name]
                return CollegeResolution(
                    matched=True,
                    status="resolved",
                    institute_name=name,
                    institute_code=entry.get("institute_code"),
                    record_id=entry.get("record_id"),
                    confidence=1.0,
                    match_type="code",
                )

        norm_query = normalize_text(query)

        # 3. Exact normalized name match
        if norm_query in self._norm_to_canonical:
            name = self._norm_to_canonical[norm_query]
            entry = self._name_index[name]
            return CollegeResolution(
                matched=True,
                status="resolved",
                institute_name=name,
                institute_code=entry.get("institute_code"),
                record_id=entry.get("record_id"),
                confidence=1.0,
                match_type="exact_name",
            )

        # 4. Check if any registered college name is fully contained in query
        contained_matches: List[Tuple[str, str]] = []  # (norm_name, canonical_name)
        for norm_name, canonical in self._norm_to_canonical.items():
            if len(norm_name) > 8 and norm_name in norm_query:
                contained_matches.append((norm_name, canonical))

        if contained_matches:
            # Sort by length descending - most specific match first
            contained_matches.sort(key=lambda x: len(x[0]), reverse=True)
            longest_norm, best_name = contained_matches[0]

            # Check if there are other matches of similar length that conflict
            conflicts = [
                canonical
                for n_name, canonical in contained_matches
                if abs(len(n_name) - len(longest_norm)) < 4 and canonical != best_name
            ]
            if conflicts:
                all_cands = [best_name] + conflicts
                cand_objs = [
                    ResolutionCandidate(
                        institute_name=c,
                        institute_code=self._name_index[c].get("institute_code"),
                        record_id=self._name_index[c].get("record_id"),
                        score=0.9,
                        match_type="contained",
                    )
                    for c in all_cands[:5]
                ]
                return CollegeResolution(
                    matched=False,
                    status="needs_clarification",
                    confidence=0.5,
                    match_type="contained_ambiguous",
                    candidates=cand_objs,
                    message=f"Multiple colleges match your query: {', '.join(all_cands[:3])}. Please specify the exact college name or institute code.",
                )

            entry = self._name_index[best_name]
            return CollegeResolution(
                matched=True,
                status="resolved",
                institute_name=best_name,
                institute_code=entry.get("institute_code"),
                record_id=entry.get("record_id"),
                confidence=0.95,
                match_type="contained",
            )

        # 5. Subphrase & Shared Prefix Match with Ambiguity Detection
        candidate_phrases = extract_query_candidate_phrases(query)
        for phrase in candidate_phrases:
            if len(phrase) < 4:
                continue

            matching_colleges: List[str] = []
            for norm_name, canonical in self._norm_to_canonical.items():
                if phrase in norm_name:
                    matching_colleges.append(canonical)

            if matching_colleges:
                matching_colleges = list(dict.fromkeys(matching_colleges))

                if len(matching_colleges) == 1:
                    matched_name = matching_colleges[0]
                    entry = self._name_index[matched_name]
                    return CollegeResolution(
                        matched=True,
                        status="resolved",
                        institute_name=matched_name,
                        institute_code=entry.get("institute_code"),
                        record_id=entry.get("record_id"),
                        confidence=0.9,
                        match_type="subphrase",
                    )
                else:
                    # Multiple colleges contain this phrase
                    # Check if the query has distinguishing keywords (e.g. city/location)
                    differentiated: List[str] = []
                    for c in matching_colleges:
                        c_norm = normalize_text(c)
                        diff_tokens = set(c_norm.split()) - set(phrase.split()) - STOP_WORDS
                        if any(dt in norm_query for dt in diff_tokens):
                            differentiated.append(c)

                    if len(differentiated) == 1:
                        matched_name = differentiated[0]
                        entry = self._name_index[matched_name]
                        return CollegeResolution(
                            matched=True,
                            status="resolved",
                            institute_name=matched_name,
                            institute_code=entry.get("institute_code"),
                            record_id=entry.get("record_id"),
                            confidence=0.9,
                            match_type="subphrase_differentiated",
                        )

                    cand_objs = [
                        ResolutionCandidate(
                            institute_name=c,
                            institute_code=self._name_index[c].get("institute_code"),
                            record_id=self._name_index[c].get("record_id"),
                            score=0.85,
                            match_type="phrase_ambiguous",
                        )
                        for c in matching_colleges[:5]
                    ]
                    return CollegeResolution(
                        matched=False,
                        status="needs_clarification",
                        confidence=0.5,
                        match_type="phrase_ambiguous",
                        candidates=cand_objs,
                        message=f"Multiple colleges match your query: {', '.join(matching_colleges[:4])}. Please specify the exact college name or institute code.",
                    )

        # 6. Token Overlap Search
        query_tokens = extract_significant_tokens(query)
        if query_tokens:
            token_candidates: List[Tuple[float, str]] = []
            for norm_name, canonical in self._norm_to_canonical.items():
                name_tokens = extract_significant_tokens(canonical)
                if not name_tokens:
                    continue
                intersection = query_tokens & name_tokens
                if len(intersection) >= 2:
                    overlap_score = len(intersection) / len(name_tokens)
                    token_candidates.append((overlap_score, canonical))

            if token_candidates:
                token_candidates.sort(key=lambda x: x[0], reverse=True)
                top_score, top_name = token_candidates[0]

                close_candidates = [
                    name for score, name in token_candidates if (top_score - score) < 0.15 and score >= 0.4
                ]
                if len(close_candidates) > 1 and top_score < 0.85:
                    cand_objs = [
                        ResolutionCandidate(
                            institute_name=c,
                            institute_code=self._name_index[c].get("institute_code"),
                            record_id=self._name_index[c].get("record_id"),
                            score=0.7,
                            match_type="token_ambiguous",
                        )
                        for c in close_candidates[:5]
                    ]
                    return CollegeResolution(
                        matched=False,
                        status="needs_clarification",
                        confidence=top_score,
                        match_type="token_ambiguous",
                        candidates=cand_objs,
                        message=f"Query matched multiple colleges: {', '.join(close_candidates[:4])}. Please specify the exact college name or code.",
                    )

                if top_score >= 0.5:
                    entry = self._name_index[top_name]
                    return CollegeResolution(
                        matched=True,
                        status="resolved",
                        institute_name=top_name,
                        institute_code=entry.get("institute_code"),
                        record_id=entry.get("record_id"),
                        confidence=round(top_score, 2),
                        match_type="token_overlap",
                    )

        # 7. Conservative fuzzy matching on names
        norm_names = list(self._norm_to_canonical.keys())
        search_target = candidate_phrases[0] if candidate_phrases else norm_query
        fuzzy_matches = difflib.get_close_matches(search_target, norm_names, n=3, cutoff=fuzzy_cutoff)
        if fuzzy_matches:
            top_fuzzy_norm = fuzzy_matches[0]
            top_canonical = self._norm_to_canonical[top_fuzzy_norm]
            sim = difflib.SequenceMatcher(None, search_target, top_fuzzy_norm).ratio()

            if len(fuzzy_matches) > 1:
                second_sim = difflib.SequenceMatcher(None, search_target, fuzzy_matches[1]).ratio()
                if (sim - second_sim) < 0.08:
                    ambig_names = [self._norm_to_canonical[m] for m in fuzzy_matches[:3]]
                    cand_objs = [
                        ResolutionCandidate(
                            institute_name=c,
                            institute_code=self._name_index[c].get("institute_code"),
                            record_id=self._name_index[c].get("record_id"),
                            score=sim,
                            match_type="fuzzy_ambiguous",
                        )
                        for c in ambig_names
                    ]
                    return CollegeResolution(
                        matched=False,
                        status="needs_clarification",
                        confidence=sim,
                        match_type="fuzzy_ambiguous",
                        candidates=cand_objs,
                        message=f"Query is ambiguous between: {', '.join(ambig_names)}. Please clarify.",
                    )

            entry = self._name_index[top_canonical]
            return CollegeResolution(
                matched=True,
                status="resolved",
                institute_name=top_canonical,
                institute_code=entry.get("institute_code"),
                record_id=entry.get("record_id"),
                confidence=round(sim, 2),
                match_type="fuzzy",
            )

        # No confident match found
        return CollegeResolution(
            matched=False,
            status="not_found",
            message="I couldn't confidently match a college name or institute code in that question. Which college do you mean?",
        )
