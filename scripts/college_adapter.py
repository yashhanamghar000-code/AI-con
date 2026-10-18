"""
Reusable College Data Adapter (Phase 1)
----------------------------------------
Converts raw sparse v4 college records (and legacy records) into a consistent,
strongly-typed, and validated internal representation (CollegeRecord).

Adheres strictly to the anti-hallucination and evidence preservation contracts:
- Preserves genuine factual values extracted from nested v4 schema structures.
- Distinguishes absent/missing fields from negative assertions.
- Does NOT mistake confidence ratings ("provided_master_list") or source names
  ("Maharashtra State CET Cell") for factual values.
- Does NOT invent fees, placements, NAAC ratings, branches, or cutoffs.
- Completely independent of the vector database or embedding models.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


IDENTITY_VALUE_FIELDS: Tuple[str, ...] = (
    "affiliation",
    "ownership",
    "institution_type",
    "city",
    "district",
    "state",
)

LEGACY_FIELDS: Tuple[str, ...] = (
    "established_year",
    "naac_grade",
    "autonomy_status",
    "approved_by",
)


def factual_value(obj: Any) -> Optional[Union[str, int, float, bool]]:
    """Extract a real stored factual value from a nested or flat structure.

    Nested v4 fields look like:
      {"value": "Sant Gadge Baba Amravati University", "source": "...", "confidence": "..."}
      {"confidence": "provided_master_list", "source": "..."}  <-- missing factual value

    Returns:
      The clean factual value (str, int, float, bool), or None if missing or conflicted.
    """
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, str):
        text = obj.strip()
        return text or None
    if isinstance(obj, dict):
        if obj.get("conflict"):
            # Conflicting source values are not resolved to a single fact
            return None
        if "value" not in obj:
            # Metadata-only object without factual value
            return None
        return factual_value(obj.get("value"))
    return None


def extract_source_attribution(obj: Any) -> Optional[str]:
    """Extract source information if present on an attribute dict."""
    if isinstance(obj, dict):
        src = obj.get("source") or obj.get("source_page")
        if isinstance(src, str) and src.strip():
            return src.strip()
    return None


def is_college_record(college_json: Any) -> bool:
    """Return True if dictionary represents a college record and not a manifest or error."""
    if not isinstance(college_json, dict) or college_json.get("error"):
        return False
    if college_json.get("institute_name"):
        return True
    record_id = college_json.get("record_id")
    return isinstance(record_id, str) and record_id.startswith("MHHEI_")


def sanitize_chroma_metadata(meta: Dict[str, Any]) -> Dict[str, Union[str, int, float, bool]]:
    """Sanitize metadata for ChromaDB compatibility.

    ChromaDB metadata values MUST be str, int, float, or bool - never None, list, or dict.
    Empty strings and None values are excluded to prevent corrupted filters.
    """
    out: Dict[str, Union[str, int, float, bool]] = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = value
        elif isinstance(value, (int, float)):
            out[key] = value
        else:
            text = str(value).strip()
            if text:
                out[key] = text
    return out


@dataclass
class PlacementMention:
    value: Union[str, int, float]
    kind: Optional[str] = None
    context: Optional[str] = None
    source: Optional[str] = None


@dataclass
class CollegeRecord:
    record_id: str
    institute_name: str
    institute_code: Optional[str] = None
    institution_type: Optional[str] = None
    official_website: Optional[str] = None
    affiliation: Optional[str] = None
    ownership: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    verification_status: Optional[str] = None
    sources_consulted: List[str] = field(default_factory=list)
    raw_facts: Dict[str, str] = field(default_factory=dict)
    source_attribution: Dict[str, str] = field(default_factory=dict)
    placement_mentions: List[PlacementMention] = field(default_factory=list)
    raw_text_pages: Dict[str, str] = field(default_factory=dict)
    schema_version: Optional[str] = None

    @property
    def stable_id(self) -> str:
        """Stable unique identifier for documents and caching."""
        if self.record_id:
            return self.record_id
        if self.institute_code:
            return self.institute_code
        name = self.institute_name or "unknown"
        clean = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
        return clean or "unknown"

    def get_primary_source(self) -> str:
        """Return the best source reference for this college."""
        if self.sources_consulted:
            return self.sources_consulted[0]
        if self.official_website:
            return self.official_website
        return "official college record"

    def get_profile_text(self) -> str:
        """Generate formatted factual text for vector indexing and LLM evidence.

        Omits any attribute where no genuine value exists.
        Never includes confidence strings ('provided_master_list') as factual values.
        """
        lines = [f"College: {self.institute_name}"]
        if self.record_id:
            lines.append(f"record_id: {self.record_id}")
        if self.institute_code:
            lines.append(f"institute_code: {self.institute_code}")
        if self.institution_type:
            lines.append(f"institution_type: {self.institution_type}")
        if self.affiliation:
            lines.append(f"affiliation: {self.affiliation}")
        if self.ownership:
            lines.append(f"ownership: {self.ownership}")
        if self.district:
            lines.append(f"district: {self.district}")
        if self.city:
            lines.append(f"city: {self.city}")
        if self.state:
            lines.append(f"state: {self.state}")
        if self.official_website:
            lines.append(f"official_website: {self.official_website}")

        # Additional legacy/verified facts if present
        for field_name in LEGACY_FIELDS:
            if field_name in self.raw_facts and field_name not in (
                "affiliation", "ownership", "institution_type", "city", "district", "state"
            ):
                lines.append(f"{field_name}: {self.raw_facts[field_name]}")

        if self.sources_consulted:
            lines.append(f"Sources consulted: {'; '.join(self.sources_consulted)}")

        return "\n".join(lines)

    def get_chroma_metadata(self, chunk_type: str = "profile") -> Dict[str, Union[str, int, float, bool]]:
        """Return Chroma-compliant metadata dictionary."""
        return sanitize_chroma_metadata({
            "record_id": self.record_id,
            "institute_name": self.institute_name,
            "institute_code": self.institute_code,
            "district": self.district,
            "state": self.state,
            "official_website": self.official_website,
            "source_page": self.get_primary_source(),
            "chunk_type": chunk_type,
        })

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "record_id": self.record_id,
            "institute_code": self.institute_code,
            "institute_name": self.institute_name,
            "institution_type": self.institution_type,
            "official_website": self.official_website,
            "affiliation": self.affiliation,
            "ownership": self.ownership,
            "city": self.city,
            "district": self.district,
            "state": self.state,
            "verification_status": self.verification_status,
            "sources_consulted": list(self.sources_consulted),
            "raw_facts": dict(self.raw_facts),
            "source_attribution": dict(self.source_attribution),
            "schema_version": self.schema_version,
        }


def adapt_college_record(raw_json: Any) -> Optional[CollegeRecord]:
    """Parse a raw JSON dict into a validated CollegeRecord.

    Extracts verified factual values while strictly ignoring confidence ratings
    and metadata-only objects. Returns None if the input is not a college record.
    """
    if not is_college_record(raw_json):
        return None

    # Base top-level fields
    record_id_val = factual_value(raw_json.get("record_id"))
    record_id = str(record_id_val) if record_id_val is not None else ""

    name_val = factual_value(raw_json.get("institute_name"))
    institute_name = str(name_val) if name_val is not None else ""

    code_val = factual_value(raw_json.get("institute_code"))
    institute_code = str(code_val) if code_val is not None else None

    website_val = factual_value(raw_json.get("official_website")) or factual_value(raw_json.get("url"))
    official_website = str(website_val) if website_val is not None else None

    type_val = factual_value(raw_json.get("institution_type"))
    institution_type = str(type_val) if type_val is not None else None

    raw_facts: Dict[str, str] = {}
    source_attribution: Dict[str, str] = {}

    extracted = raw_json.get("extracted")
    if not isinstance(extracted, dict):
        extracted = {}

    # Nested identity fields
    identity = extracted.get("identity")
    if not isinstance(identity, dict):
        identity = {}

    # Verification status
    v_status = identity.get("verification_status")
    verification_status_val = factual_value(v_status)
    verification_status = str(verification_status_val) if verification_status_val is not None else None

    # Extract factual values from identity
    for field_name in IDENTITY_VALUE_FIELDS:
        obj = identity.get(field_name)
        val = factual_value(obj)
        # Fall back to root or flat extracted if missing from identity
        if val is None and field_name in extracted:
            obj = extracted.get(field_name)
            val = factual_value(obj)
        if val is not None:
            raw_facts[field_name] = str(val)
            src = extract_source_attribution(obj)
            if src:
                source_attribution[field_name] = src

    # Location section fallback for city, district, state
    location = extracted.get("location")
    if isinstance(location, dict):
        for field_name in ("city", "district", "state"):
            if field_name not in raw_facts:
                loc_obj = location.get(field_name)
                val = factual_value(loc_obj)
                if val is not None:
                    raw_facts[field_name] = str(val)
                    src = extract_source_attribution(loc_obj)
                    if src:
                        source_attribution[field_name] = src

    # Legacy fields (established_year, naac_grade, etc.)
    for field_name in LEGACY_FIELDS:
        if field_name not in raw_facts:
            legacy_obj = extracted.get(field_name)
            val = factual_value(legacy_obj)
            if val is not None:
                raw_facts[field_name] = str(val)
                src = extract_source_attribution(legacy_obj)
                if src:
                    source_attribution[field_name] = src

    # Sources consulted list
    sources: List[str] = []
    sources_raw = raw_json.get("sources_consulted")
    if isinstance(sources_raw, list):
        for s in sources_raw:
            if isinstance(s, str) and s.strip():
                sources.append(s.strip())

    # Placement mentions
    placement_mentions: List[PlacementMention] = []
    for pm in extracted.get("placement_mentions") or []:
        if isinstance(pm, dict):
            pm_val = factual_value(pm.get("value"))
            if pm_val is not None:
                placement_mentions.append(PlacementMention(
                    value=pm_val,
                    kind=factual_value(pm.get("kind")),
                    context=factual_value(pm.get("context")),
                    source=extract_source_attribution(pm) or (sources[0] if sources else None),
                ))

    # Raw text pages
    raw_text_pages: Dict[str, str] = {}
    raw_pages = raw_json.get("raw_text_pages")
    if isinstance(raw_pages, dict):
        for u, t in raw_pages.items():
            if isinstance(u, str) and isinstance(t, str) and t.strip():
                raw_text_pages[u] = t.strip()

    # Determine resolved values
    affiliation = raw_facts.get("affiliation")
    ownership = raw_facts.get("ownership")
    city = raw_facts.get("city")
    district = raw_facts.get("district")
    state = raw_facts.get("state")
    if not institution_type:
        institution_type = raw_facts.get("institution_type")

    return CollegeRecord(
        record_id=record_id,
        institute_name=institute_name,
        institute_code=institute_code,
        institution_type=institution_type,
        official_website=official_website,
        affiliation=affiliation,
        ownership=ownership,
        city=city,
        district=district,
        state=state,
        verification_status=verification_status,
        sources_consulted=sources,
        raw_facts=raw_facts,
        source_attribution=source_attribution,
        placement_mentions=placement_mentions,
        raw_text_pages=raw_text_pages,
        schema_version=str(raw_json.get("schema_version") or "4.0"),
    )
