"""
Qwen Generation and Evidence Grounding (Task 14)
-----------------------------------------------
Provides structured payload construction, strict anti-hallucination prompting,
JSON schema validation, and fallback to deterministic tables for local LLM generation.

Anti-Hallucination Contracts (Task 14):
1. Keep all filtering, mathematical calculations, and cutoff retrieval outside LLM.
2. Supply compact structured evidence payload.
3. Require structured JSON before rendering natural language prose.
4. Validate JSON responses against strict schema; retry once on failure or fallback to deterministic table.
5. Rebuff adversarial prompts attempting to force admission guarantees or fabricated cutoffs.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

STRICT_SYSTEM_PROMPT = """You are AI-CON, the official Maharashtra Engineering Admissions Counselling Assistant.
You MUST adhere strictly to the following evidence-grounding and compliance rules:
1. Grounding: Answer ONLY using the structured evidence provided in the JSON payload.
2. Exact Identity: Preserve exact institute codes, institute names, and branch names without abbreviation or truncation.
3. No Fabrication: NEVER invent or estimate cutoffs, closing ranks, fees, packages, popularity scores, or citations not present in the evidence.
4. Distinction: Clearly distinguish historical past cutoffs from 2026-27 ML predictions.
5. Missing Data: When evidence is missing, explicitly state that data is unavailable.
6. No Guarantees: NEVER state or imply that admission or allotment is guaranteed or 100% safe. Always use 'historically more attainable' or 'competitive'.
7. Response Format: Return valid JSON matching the specified schema.
"""


@dataclass
class GroundedResponse:
    is_valid: bool
    status: str  # "validated_json" | "repaired_json" | "deterministic_fallback" | "llm_refusal"
    structured_data: Dict[str, Any]
    prose_response: str
    validation_errors: List[str] = field(default_factory=list)


class QwenPayloadBuilder:
    """Builds compact structured evidence payloads for LLM grounding."""

    @staticmethod
    def build_payload(
        student_profile: Dict[str, Any],
        intent: str,
        colleges: List[Dict[str, Any]],
        evidence_records: Optional[List[Dict[str, Any]]] = None,
        missing_data_flags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Constructs a deterministic structured dictionary for Qwen."""
        sanitized_colleges = []
        for c in colleges:
            sanitized_colleges.append({
                "institute_code": str(c.get("institute_code")),
                "institute_name": str(c.get("institute_name")),
                "branch": str(c.get("branch", "Engineering")),
                "historical_cutoff": {
                    "percentile": c.get("cutoff_percentile"),
                    "closing_rank": c.get("closing_rank"),
                    "round": c.get("round_no", 1),
                    "year": c.get("academic_year", "2024-25"),
                    "evidence_id": c.get("evidence_id"),
                },
                "ml_prediction": {
                    "predicted_cutoff": c.get("predicted_cutoff"),
                    "predicted_rank": c.get("predicted_rank"),
                    "status": "statistical_estimate" if c.get("predicted_cutoff") is not None else "unavailable",
                },
                "popularity_evaluation": {
                    "available": c.get("popularity_available", False),
                    "score": c.get("popularity_score"),
                },
                "roi_evaluation": {
                    "computable": c.get("roi_computable", False),
                    "summary": c.get("roi_tier", "Not computable"),
                },
                "admission_feasibility": c.get("tier", "Competitive"),
            })

        payload = {
            "query_intent": intent,
            "student_profile": {
                "percentile": student_profile.get("percentile"),
                "merit_rank": student_profile.get("merit_rank"),
                "category": student_profile.get("category", "GOPENS"),
                "location": student_profile.get("location"),
                "preferred_branches": student_profile.get("preferred_branches", []),
            },
            "candidate_institutes": sanitized_colleges,
            "missing_data_flags": missing_data_flags or [],
            "grounding_rules": [
                "Admission to Maharashtra engineering colleges is administered strictly by CET Cell CAP rounds.",
                "No cutoffs may be fabricated.",
                "Safe admission promises are prohibited.",
            ],
        }
        return payload


class QwenResponseValidator:
    """Validates structured JSON output from Qwen against ground truth payload."""

    REQUIRED_KEYS = ["summary", "colleges", "data_limitations", "disclaimer"]

    @staticmethod
    def validate(
        llm_response_text: str,
        payload: Dict[str, Any],
    ) -> Tuple[bool, Optional[Dict[str, Any]], List[str]]:
        """Validate LLM JSON output against schema and payload evidence."""
        errors = []
        # Extract JSON from potential code fences or raw text
        json_str = llm_response_text.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_str, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            first_brace = json_str.find("{")
            last_brace = json_str.rfind("}")
            if first_brace != -1 and last_brace != -1:
                json_str = json_str[first_brace:last_brace + 1]

        try:
            parsed = json.loads(json_str)
        except Exception as exc:
            return False, None, [f"JSON parse error: {exc}"]

        # Check required schema keys
        for key in QwenResponseValidator.REQUIRED_KEYS:
            if key not in parsed:
                errors.append(f"Missing required key: '{key}'")

        # Check hallucination: Every college in output must exist in input payload
        known_codes = {str(c["institute_code"]) for c in payload.get("candidate_institutes", [])}
        out_colleges = parsed.get("colleges", [])
        if isinstance(out_colleges, list):
            for oc in out_colleges:
                c_code = str(oc.get("institute_code", ""))
                if c_code and c_code not in known_codes:
                    errors.append(f"Hallucinated institute_code: '{c_code}' not in payload.")

        # Check for banned guarantee words in output
        full_text = json.dumps(parsed).lower()
        banned_phrases = ["guaranteed admission", "100% guarantee", "100% guaranteed", "promise you a seat"]
        for phrase in banned_phrases:
            if phrase in full_text:
                errors.append(f"Illegal guarantee phrase detected: '{phrase}'")

        return len(errors) == 0, parsed, errors


class QwenGroundingEngine:
    """Orchestrates structured payload generation, Qwen prompting, and fallback handling."""

    def __init__(self, llm_callable: Optional[Callable[[str, str], str]] = None):
        self.llm_callable = llm_callable

    def generate_grounded_response(
        self,
        payload: Dict[str, Any],
        user_question: str,
    ) -> GroundedResponse:
        """Generate response with validation, repair retry, or deterministic fallback."""
        # 1. Deterministic Fallback if LLM unavailable
        if self.llm_callable is None:
            return self._build_deterministic_fallback(payload, "LLM not configured; returning verified deterministic evidence.")

        # 2. Check for explicit adversarial prompts
        q_lower = user_question.lower()
        if any(g in q_lower for g in ["guarantee me", "promise me", "100% seat", "confirm my admission"]):
            return GroundedResponse(
                is_valid=True,
                status="llm_refusal",
                structured_data={"refusal": True, "reason": "No admission guarantees can be made under statutory CAP rules."},
                prose_response=(
                    "Under Maharashtra State CET Cell statutory rules, engineering admissions are allocated "
                    "strictly through merit rank and choice-form preference rounds. No counsellor or model can guarantee admission. "
                    "Colleges with past cutoffs below your score are categorized as 'historically more attainable'."
                ),
            )

        # 3. Call LLM with structured payload
        prompt = (
            f"User Question: {user_question}\n\n"
            f"Evidence JSON Payload:\n{json.dumps(payload, indent=2)}\n\n"
            "Respond ONLY with a JSON object adhering to this schema:\n"
            "{\n"
            '  "summary": "High-level overview grounded in evidence",\n'
            '  "colleges": [{"institute_code": "...", "institute_name": "...", "status": "historically_attainable|competitive|reach"}],\n'
            '  "data_limitations": ["Any missing popularity or ROI facts"],\n'
            '  "disclaimer": "Statutory CAP disclaimer"\n'
            "}"
        )

        try:
            raw_out = self.llm_callable(STRICT_SYSTEM_PROMPT, prompt)
        except Exception as exc:
            logger.warning(f"Qwen LLM call failed: {exc}. Using deterministic fallback.")
            return self._build_deterministic_fallback(payload, f"LLM service call failed: {exc}")

        # 4. Validate output
        is_valid, parsed_json, errors = QwenResponseValidator.validate(raw_out, payload)
        if is_valid and parsed_json:
            prose = self._render_prose_from_json(parsed_json)
            return GroundedResponse(
                is_valid=True,
                status="validated_json",
                structured_data=parsed_json,
                prose_response=prose,
            )

        # 5. Retry once with repair prompt
        logger.info(f"LLM output failed validation ({errors}). Attempting repair...")
        repair_prompt = (
            f"Your previous output contained schema/validation errors:\n{errors}\n\n"
            "Please return ONLY valid JSON matching the schema without markdown or extra commentary."
        )
        try:
            repaired_out = self.llm_callable(STRICT_SYSTEM_PROMPT, repair_prompt)
            is_valid_rep, parsed_rep, rep_errors = QwenResponseValidator.validate(repaired_out, payload)
            if is_valid_rep and parsed_rep:
                prose = self._render_prose_from_json(parsed_rep)
                return GroundedResponse(
                    is_valid=True,
                    status="repaired_json",
                    structured_data=parsed_rep,
                    prose_response=prose,
                )
        except Exception:
            pass

        # 6. Fallback to deterministic evidence table
        return self._build_deterministic_fallback(payload, f"Validation failure: {errors}")

    def _build_deterministic_fallback(self, payload: Dict[str, Any], note: str) -> GroundedResponse:
        """Constructs a deterministic markdown table directly from payload facts."""
        colleges = payload.get("candidate_institutes", [])
        lines = [
            "### 🎯 Verified College Evidence Table",
            f"*{note}*",
            "",
            "| Code | Institute Name | Branch | Past Cutoff | 2026-27 Est | Feasibility |",
            "|---|---|---|---|---|---|",
        ]
        for c in colleges:
            cut = c.get("historical_cutoff", {})
            pct_str = f"{cut.get('percentile'):.2f}%" if cut.get("percentile") is not None else "N/A"
            ml = c.get("ml_prediction", {})
            ml_str = f"~{ml.get('predicted_cutoff'):.2f}%" if ml.get("predicted_cutoff") is not None else "Unavailable"
            lines.append(
                f"| `{c['institute_code']}` | {c['institute_name']} | {c['branch']} | {pct_str} | {ml_str} | {c.get('admission_feasibility', 'Competitive')} |"
            )

        lines.append("\n*Notice: Grounded strictly in official DTE Maharashtra historical data. No admission guaranteed.*")
        return GroundedResponse(
            is_valid=True,
            status="deterministic_fallback",
            structured_data=payload,
            prose_response="\n".join(lines),
            validation_errors=[note],
        )

    def _render_prose_from_json(self, data: Dict[str, Any]) -> str:
        """Render clean, readable prose from validated JSON data."""
        lines = [data.get("summary", "")]
        lines.append("")
        for idx, c in enumerate(data.get("colleges", []), 1):
            lines.append(f"{idx}. **{c.get('institute_name')}** (Code: `{c.get('institute_code')}`) — *{c.get('status', 'Competitive')}*")
        lines.append("")
        if data.get("data_limitations"):
            lines.append("**Data Limitations:**")
            for lim in data["data_limitations"]:
                lines.append(f"• {lim}")
        if data.get("disclaimer"):
            lines.append(f"\n*{data['disclaimer']}*")
        return "\n".join(lines)
