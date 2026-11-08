"""
CutoffEvidence: Typed, validated evidence records for Maharashtra CAP cutoff data.

Design constraints (AI_CON_IMPROVEMENT_PLAN.md Task 6):
- Never silently select results[0] without filtering criteria
- Never mix rank and percentile fields (both may be None, but neither is fabricated)
- Never mix different quota/category/seat-pool records
- Evidence ID must carry year, round, stage, category, institute_code
- Missing values stay None — never fabricated or zero-filled
- Closing rank == 1 when percentile > 90 is flagged as a likely ML fallback, not shown as fact
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Known valid category tokens in Maharashtra CAP admission data
# ---------------------------------------------------------------------------
_VALID_CATEGORIES: frozenset[str] = frozenset(
    [
        # Open / General
        "GOPENS", "LOPENS",
        # OBC
        "GOBCS", "LOBCS",
        # SC
        "GSCS", "LSCS",
        # ST
        "GSTS", "LSTS",
        # NT (Nomadic Tribes) variants
        "GNT1S", "LNT1S", "GNT2S", "LNT2S", "GNT3S", "LNT3S",
        # VJ/DT
        "GVJS", "LVJS",
        # EWS
        "EWSS", "EWS",
        # Tuition Fee Waiver Scheme
        "TFWS",
        # Defence
        "DEFOPENS", "DEFOBCS", "DEFROBCS", "DEFGSTS",
        # Persons with Disability
        "PWDOPENS",
        # Minority
        "MI",
        # Orphan
        "ORPHAN",
        # J&K Migrant
        "JKS",
        # Home University
        "GOPENH", "LOPENH",
        # Other Than Home University
        "GOPENO", "LOPENO",
    ]
)

# Academic years we have data for
_KNOWN_YEARS: frozenset[str] = frozenset(
    ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
)

# Evidence ID format: "YYYY-YY:CCCCC:XXXXXXXXXX:level_key:CATEGORY:RN:SN"
# level_key is lowercase (e.g. state_level, home_university), CATEGORY is uppercase.
# or legacy "EV-CCCCC-..." 
_EVIDENCE_ID_COLON_RE = re.compile(
    r"^\d{4}-\d{2}:\d{5}:.+:[a-zA-Z0-9_]+:.+:R\d+:S\d+$"
)
_EVIDENCE_ID_EV_RE = re.compile(
    r"^EV-\d{5}-.*$"
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_percentile(value: Optional[float], field_name: str = "percentile") -> Optional[float]:
    """Return validated percentile or None. Raises ValueError for out-of-range."""
    if value is None:
        return None
    v = float(value)
    if v < 0.0 or v > 100.0:
        raise ValueError(f"{field_name} must be in [0.0, 100.0], got {v}")
    return v


def _validate_rank(value: Optional[int], field_name: str = "rank") -> Optional[int]:
    """Return validated rank or None. Raises ValueError for < 1."""
    if value is None:
        return None
    r = int(value)
    if r < 1:
        raise ValueError(f"{field_name} must be >= 1, got {r}")
    return r


def _is_rank_one_suspicious(rank: Optional[int], percentile: Optional[float]) -> bool:
    """Return True when rank==1 AND percentile>90 — almost certainly an ML/fallback artifact."""
    return rank == 1 and percentile is not None and percentile > 90.0


def validate_evidence_id(evidence_id: str) -> Tuple[bool, str]:
    """
    Check whether an evidence_id string is correctly structured.

    Returns (is_valid: bool, reason: str).
    A valid evidence_id must:
      - Follow colon-delimited format "YYYY-YY:CCCCC:...:CATEGORY:RN:SN", OR
      - Follow legacy "EV-CCCCC-..." format.
    """
    if not evidence_id:
        return False, "evidence_id is empty or None"
    s = str(evidence_id).strip()
    if _EVIDENCE_ID_COLON_RE.match(s):
        return True, "ok"
    if _EVIDENCE_ID_EV_RE.match(s):
        return True, "ok (legacy EV- format)"
    return False, f"evidence_id '{s}' does not match expected patterns"


# ---------------------------------------------------------------------------
# CutoffEvidence dataclass
# ---------------------------------------------------------------------------

@dataclass
class CutoffEvidence:
    """
    A single, fully-attributed, validated cutoff record.

    Rules enforced at construction:
    - percentile validated in [0, 100] or None
    - rank validated >= 1 or None
    - rank == 1 with percentile > 90 raises a warning (likely ML fallback)
    - at least one of (closing_rank, closing_percentile) must be non-None
    - evidence_id validated for format
    - category optionally checked against known CAP tokens
    """

    # Mandatory identification fields
    evidence_id: str
    institute_code: str           # always 5-digit zero-padded
    institute_name: str
    branch: str
    category: str
    academic_year: str

    # Mandatory round/stage/quota provenance
    cap_round: int
    stage: str
    list_type: str

    # The actual cutoff values — both may be None if data source is incomplete
    closing_rank: Optional[int] = None
    closing_percentile: Optional[float] = None

    # Optional source traceability
    source_file: Optional[str] = None
    page: Optional[int] = None

    # Validation flags set at post-init
    is_rank_suspicious: bool = field(init=False, default=False)
    validation_warnings: List[str] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        # Normalize institute_code to 5 digits
        code = str(self.institute_code).strip()
        if len(code) == 4 and code.isdigit():
            code = code.zfill(5)
        self.institute_code = code

        # Validate percentile
        try:
            self.closing_percentile = _validate_percentile(self.closing_percentile)
        except ValueError as exc:
            raise ValueError(f"CutoffEvidence for {self.institute_code}: {exc}") from exc

        # Validate rank
        try:
            self.closing_rank = _validate_rank(self.closing_rank)
        except ValueError as exc:
            raise ValueError(f"CutoffEvidence for {self.institute_code}: {exc}") from exc

        # At least one must be present
        if self.closing_rank is None and self.closing_percentile is None:
            raise ValueError(
                f"CutoffEvidence for {self.institute_code}/{self.branch}/{self.category}: "
                "both closing_rank and closing_percentile are None — cannot create a record with no data."
            )

        # Warn on suspicious rank=1 with high percentile
        if _is_rank_one_suspicious(self.closing_rank, self.closing_percentile):
            msg = (
                f"CutoffEvidence WARNING: closing_rank=1 with closing_percentile={self.closing_percentile} "
                f"for {self.institute_code}/{self.branch}/{self.category} — "
                "this is likely an ML fallback artifact, not an official CET Cell record."
            )
            self.is_rank_suspicious = True
            self.validation_warnings.append(msg)
            warnings.warn(msg, UserWarning, stacklevel=2)

        # Validate evidence_id format
        ok, reason = validate_evidence_id(self.evidence_id)
        if not ok:
            self.validation_warnings.append(
                f"evidence_id format warning: {reason}. "
                "Evidence IDs should include year, institute code, category, round, and stage."
            )

        # Warn on unknown category tokens
        cat_upper = str(self.category).upper()
        if cat_upper not in _VALID_CATEGORIES:
            self.validation_warnings.append(
                f"Category '{self.category}' not in known Maharashtra CAP quota tokens. "
                "This may be valid (new quota) or a data entry error."
            )

        # Validate academic year
        if self.academic_year not in _KNOWN_YEARS:
            self.validation_warnings.append(
                f"Academic year '{self.academic_year}' is outside expected range {sorted(_KNOWN_YEARS)}."
            )

    @classmethod
    def from_cutoff_agent_record(cls, record: Dict[str, Any]) -> "CutoffEvidence":
        """
        Construct a CutoffEvidence from a raw dict returned by CutoffAgent.get_cutoffs().

        This is the canonical bridge between raw data and typed evidence.
        Raises ValueError if the record cannot produce a valid CutoffEvidence.
        """
        ev_id = record.get("evidence_id") or ""
        # Build a synthetic evidence_id if the raw one is absent/malformed
        if not ev_id:
            code = str(record.get("institute_code", "XXXXX")).zfill(5)
            cat = str(record.get("category", "UNK")).upper()
            yr = str(record.get("academic_year", "????-??"))
            rnd = record.get("round", 1)
            stg = record.get("stage", "1")
            ev_id = f"{yr}:{code}:SYNTHETIC:{cat}:R{rnd}:S{stg}"

        return cls(
            evidence_id=ev_id,
            institute_code=str(record.get("institute_code", "")),
            institute_name=str(record.get("institute_name", "")),
            branch=str(record.get("branch", "")),
            category=str(record.get("category", "")),
            academic_year=str(record.get("academic_year", "")),
            cap_round=int(record.get("round") or 1),
            stage=str(record.get("stage") or "1"),
            list_type=str(record.get("list_type") or "CAP"),
            closing_rank=record.get("closing_rank"),
            closing_percentile=record.get("closing_percentile"),
            source_file=record.get("source_file"),
            page=record.get("page"),
        )

    def as_display_text(self) -> str:
        """Human-readable single-line evidence string — never shows fabricated fallback values."""
        rank_str = f"Rank #{self.closing_rank:,}" if self.closing_rank is not None else "Rank: N/A"
        pct_str = f"{self.closing_percentile:.4f}%" if self.closing_percentile is not None else "Percentile: N/A"
        susp = " ⚠️ [rank suspicious — possible ML fallback]" if self.is_rank_suspicious else ""
        src = f" (source: {self.source_file}, p.{self.page})" if self.source_file else ""
        return (
            f"[{self.evidence_id}] "
            f"{self.academic_year} {self.institute_name} — {self.branch} — {self.category}: "
            f"Round {self.cap_round}, Stage {self.stage}, {pct_str}, {rank_str}, "
            f"List: {self.list_type}{src}{susp}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict representation for serialization."""
        return {
            "evidence_id": self.evidence_id,
            "institute_code": self.institute_code,
            "institute_name": self.institute_name,
            "branch": self.branch,
            "category": self.category,
            "academic_year": self.academic_year,
            "cap_round": self.cap_round,
            "stage": self.stage,
            "list_type": self.list_type,
            "closing_rank": self.closing_rank,
            "closing_percentile": self.closing_percentile,
            "source_file": self.source_file,
            "page": self.page,
            "is_rank_suspicious": self.is_rank_suspicious,
            "validation_warnings": self.validation_warnings,
        }


# ---------------------------------------------------------------------------
# validate_evidence_integrity: batch validation over a list of records
# ---------------------------------------------------------------------------

@dataclass
class IntegrityReport:
    """Result of a batch integrity check on a list of CutoffEvidence records."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    suspicious_rank_count: int = 0
    invalid_evidence_id_count: int = 0
    unknown_category_count: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.failed == 0 and self.suspicious_rank_count == 0


def validate_evidence_integrity(
    records: List[CutoffEvidence],
    expected_category: Optional[str] = None,
    expected_year: Optional[str] = None,
) -> IntegrityReport:
    """
    Run integrity checks on a batch of CutoffEvidence records.

    Checks:
    1. evidence_id present and correctly formatted
    2. percentile in [0, 100]
    3. rank >= 1
    4. year in known range
    5. category matches one of the known CAP quota tokens
    6. If expected_category is set, all records match it (no pool mixing)
    7. If expected_year is set, all records match it (no year mixing)
    8. rank == 1 with high percentile flagged as suspicious
    """
    report = IntegrityReport(total=len(records))

    for ev in records:
        record_ok = True

        # Check category mixing
        if expected_category and ev.category.upper() != expected_category.upper():
            msg = (
                f"Category mismatch in {ev.evidence_id}: "
                f"expected {expected_category}, got {ev.category}. "
                "GOPENS and GSCS records must NEVER be mixed."
            )
            report.errors.append(msg)
            record_ok = False

        # Check year mixing
        if expected_year and ev.academic_year != expected_year:
            msg = (
                f"Year mismatch in {ev.evidence_id}: "
                f"expected {expected_year}, got {ev.academic_year}."
            )
            report.errors.append(msg)
            record_ok = False

        # Evidence ID check
        ok_ev, reason_ev = validate_evidence_id(ev.evidence_id)
        if not ok_ev:
            report.invalid_evidence_id_count += 1
            report.warnings.append(reason_ev)

        # Collect warnings
        for w in ev.validation_warnings:
            if "suspicious" in w.lower() or "rank=1" in w.lower():
                report.suspicious_rank_count += 1
            elif "not in known" in w.lower():
                report.unknown_category_count += 1
            report.warnings.append(w)

        if ev.is_rank_suspicious:
            report.suspicious_rank_count += 1

        if record_ok:
            report.passed += 1
        else:
            report.failed += 1

    return report


# ---------------------------------------------------------------------------
# Convenience: convert a list of raw dicts to CutoffEvidence, skipping bad ones
# ---------------------------------------------------------------------------

def records_to_evidence(
    raw_records: List[Dict[str, Any]],
    skip_suspicious_rank: bool = False,
) -> List[CutoffEvidence]:
    """
    Convert raw dicts from CutoffAgent.get_cutoffs() to CutoffEvidence instances.

    - Records that fail validation are logged to stderr and skipped.
    - If skip_suspicious_rank=True, records where rank==1 AND percentile>90 are excluded.
    """
    import sys
    result: List[CutoffEvidence] = []
    for raw in raw_records:
        try:
            ev = CutoffEvidence.from_cutoff_agent_record(raw)
            if skip_suspicious_rank and ev.is_rank_suspicious:
                print(
                    f"[cutoff_evidence] Skipping suspicious rank=1 record: {ev.evidence_id}",
                    file=sys.stderr,
                )
                continue
            result.append(ev)
        except ValueError as exc:
            print(f"[cutoff_evidence] Skipping invalid record: {exc}", file=sys.stderr)
    return result
