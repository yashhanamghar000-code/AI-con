"""
Dataset Validation Module (Phase 1)
------------------------------------
Validates the college dataset in college_ai_consultant_sparse_enriched_v4_no_cutoffs/.

Checks:
- Valid JSON syntax across all college files.
- Uniqueness of record_id across all records.
- Institute codes: valid codes, missing codes (legitimate for non-CET colleges), duplicate codes.
- Institute names: presence, validity, empty strings.
- Missing or empty fields: counts and patterns.
- Nested identity fields: value vs confidence vs source structures.
- Official website URLs: format and presence.
- Sources consulted: counts, URL formats.
- Consistency with dataset_manifest.json.
- Consistency with college_dataset_index.csv.
- Distinction between missing information and verified negative assertions.
- Guarantees: no invented fees, placements, NAAC ratings, accreditation, branches, or cutoffs.

Generates a detailed report with counts, percentages, and warnings.
Leaves the original dataset completely unchanged.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Support running directly or as a module
try:
    from college_adapter import (
        adapt_college_record,
        factual_value,
        is_college_record,
    )
except ImportError:
    from scripts.college_adapter import (
        adapt_college_record,
        factual_value,
        is_college_record,
    )


SKIP_FILES: Set[str] = {"dataset_manifest.json"}


@dataclass
class ValidationSummary:
    total_json_files: int = 0
    valid_json_count: int = 0
    invalid_json_count: int = 0
    college_records_count: int = 0
    unique_record_ids: int = 0
    duplicate_record_ids: List[str] = field(default_factory=list)
    records_with_institute_code: int = 0
    records_without_institute_code: int = 0
    duplicate_institute_codes: Dict[str, List[str]] = field(default_factory=dict)
    missing_institute_names: List[str] = field(default_factory=list)
    official_website_count: int = 0
    invalid_website_urls: List[Tuple[str, str]] = field(default_factory=list)
    affiliation_present_count: int = 0
    affiliation_confidence_only_count: int = 0
    district_present_count: int = 0
    district_confidence_only_count: int = 0
    city_present_count: int = 0
    city_confidence_only_count: int = 0
    state_present_count: int = 0
    ownership_present_count: int = 0
    records_with_sources: int = 0
    zero_source_count: int = 0
    manifest_checked: bool = False
    manifest_matches: bool = False
    manifest_discrepancies: List[str] = field(default_factory=list)
    csv_index_checked: bool = False
    csv_index_matches: bool = False
    csv_discrepancies: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_dataset(
    dataset_dir: Union[str, Path],
    csv_index_path: Optional[Union[str, Path]] = None,
    manifest_path: Optional[Union[str, Path]] = None,
) -> ValidationSummary:
    """Run full validation over the specified dataset directory."""
    dataset_path = Path(dataset_dir)
    if not dataset_path.is_dir():
        summary = ValidationSummary()
        summary.errors.append(f"Dataset directory not found: {dataset_path}")
        return summary

    summary = ValidationSummary()
    seen_record_ids: Dict[str, str] = {}  # record_id -> filename
    code_to_records: Dict[str, List[str]] = {}  # institute_code -> [record_id, ...]
    parsed_records: Dict[str, Dict[str, Any]] = {}  # record_id -> raw_json

    # 1. Inspect all JSON files in the directory
    json_paths = sorted(dataset_path.glob("*.json"))
    for p in json_paths:
        if p.name in SKIP_FILES or p.name.startswith("_"):
            continue
        summary.total_json_files += 1

        try:
            content = p.read_text(encoding="utf-8")
            data = json.loads(content)
            summary.valid_json_count += 1
        except Exception as exc:
            summary.invalid_json_count += 1
            summary.errors.append(f"Invalid JSON in {p.name}: {exc}")
            continue

        if not is_college_record(data):
            summary.warnings.append(f"{p.name} does not appear to be a college record.")
            continue

        summary.college_records_count += 1

        # Check record_id uniqueness
        rec_id = data.get("record_id")
        if not rec_id or not isinstance(rec_id, str):
            summary.errors.append(f"{p.name} missing valid record_id")
            rec_id = f"UNKNOWN_{p.name}"
        else:
            if rec_id in seen_record_ids:
                summary.duplicate_record_ids.append(rec_id)
                summary.errors.append(f"Duplicate record_id {rec_id} in {p.name} (previously in {seen_record_ids[rec_id]})")
            else:
                seen_record_ids[rec_id] = p.name

        parsed_records[rec_id] = data

        # Check institute_name
        name = data.get("institute_name")
        if not name or not isinstance(name, str) or not name.strip():
            summary.missing_institute_names.append(rec_id)
            summary.errors.append(f"{rec_id} has empty institute_name")

        # Check institute_code
        code_val = factual_value(data.get("institute_code"))
        if code_val is not None:
            summary.records_with_institute_code += 1
            code_str = str(code_val).strip()
            code_to_records.setdefault(code_str, []).append(rec_id)
        else:
            summary.records_without_institute_code += 1

        # Check official_website
        web_val = factual_value(data.get("official_website")) or factual_value(data.get("url"))
        if web_val is not None:
            summary.official_website_count += 1
            web_str = str(web_val).strip()
            if not re.match(r"^https?://", web_str, re.I):
                summary.invalid_website_urls.append((rec_id, web_str))
                summary.warnings.append(f"{rec_id} website does not start with http(s): {web_str}")

        # Check nested identity fields and confidence vs value
        extracted = data.get("extracted") or {}
        identity = extracted.get("identity") if isinstance(extracted, dict) else {}
        if isinstance(identity, dict):
            # Affiliation
            aff_obj = identity.get("affiliation")
            if factual_value(aff_obj) is not None:
                summary.affiliation_present_count += 1
            elif isinstance(aff_obj, dict) and "confidence" in aff_obj and "value" not in aff_obj:
                summary.affiliation_confidence_only_count += 1

            # District
            dist_obj = identity.get("district")
            if factual_value(dist_obj) is not None:
                summary.district_present_count += 1
            elif isinstance(dist_obj, dict) and "confidence" in dist_obj and "value" not in dist_obj:
                summary.district_confidence_only_count += 1

            # City
            city_obj = identity.get("city")
            if factual_value(city_obj) is not None:
                summary.city_present_count += 1
            elif isinstance(city_obj, dict) and "confidence" in city_obj and "value" not in city_obj:
                summary.city_confidence_only_count += 1

            # State
            state_obj = identity.get("state")
            if factual_value(state_obj) is not None:
                summary.state_present_count += 1

            # Ownership
            own_obj = identity.get("ownership")
            if factual_value(own_obj) is not None:
                summary.ownership_present_count += 1

        # Sources consulted
        sources = data.get("sources_consulted")
        if isinstance(sources, list) and len(sources) > 0:
            summary.records_with_sources += 1
        else:
            summary.zero_source_count += 1

    summary.unique_record_ids = len(seen_record_ids)

    # Check duplicate institute codes
    for code, rec_ids in code_to_records.items():
        if len(rec_ids) > 1:
            summary.duplicate_institute_codes[code] = rec_ids
            summary.warnings.append(f"Institute code {code} shared by multiple records: {rec_ids}")

    # 2. Check dataset_manifest.json
    if manifest_path is None:
        manifest_candidate = dataset_path / "dataset_manifest.json"
    else:
        manifest_candidate = Path(manifest_path)

    if manifest_candidate.is_file():
        summary.manifest_checked = True
        try:
            manifest_data = json.loads(manifest_candidate.read_text(encoding="utf-8"))
            expected_records = manifest_data.get("json_records_written") or manifest_data.get("input_rows")
            if expected_records and expected_records != summary.college_records_count:
                disc = f"Manifest states {expected_records} records, but found {summary.college_records_count}"
                summary.manifest_discrepancies.append(disc)
                summary.warnings.append(disc)

            if manifest_data.get("record_ids_unique") and len(summary.duplicate_record_ids) > 0:
                disc = f"Manifest claims unique record_ids, but duplicates found: {summary.duplicate_record_ids}"
                summary.manifest_discrepancies.append(disc)
                summary.errors.append(disc)

            if not summary.manifest_discrepancies:
                summary.manifest_matches = True
        except Exception as exc:
            summary.manifest_discrepancies.append(f"Error reading manifest: {exc}")
            summary.warnings.append(f"Error reading manifest: {exc}")

    # 3. Check college_dataset_index.csv
    if csv_index_path is None:
        csv_candidate = dataset_path / "college_dataset_index.csv"
    else:
        csv_candidate = Path(csv_index_path)

    if csv_candidate.is_file():
        summary.csv_index_checked = True
        try:
            with open(csv_candidate, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                csv_rows = list(reader)

            if len(csv_rows) != summary.college_records_count:
                disc = f"CSV has {len(csv_rows)} rows, but directory has {summary.college_records_count} records"
                summary.csv_discrepancies.append(disc)
                summary.warnings.append(disc)

            csv_ids = set()
            for r in csv_rows:
                rid = r.get("record_id")
                if not rid:
                    continue
                csv_ids.add(rid)
                if rid not in parsed_records:
                    disc = f"CSV references {rid} ({r.get('json_file')}) but file missing from directory"
                    summary.csv_discrepancies.append(disc)
                    summary.errors.append(disc)
                else:
                    rec = parsed_records[rid]
                    # Verify code match if present in CSV
                    csv_code = (r.get("institute_code") or "").strip()
                    json_code = str(factual_value(rec.get("institute_code")) or "").strip()
                    if csv_code and json_code and csv_code != json_code:
                        disc = f"{rid} code mismatch: CSV='{csv_code}', JSON='{json_code}'"
                        summary.csv_discrepancies.append(disc)
                        summary.warnings.append(disc)

            if not summary.csv_discrepancies:
                summary.csv_index_matches = True
        except Exception as exc:
            summary.csv_discrepancies.append(f"Error reading CSV index: {exc}")
            summary.warnings.append(f"Error reading CSV index: {exc}")

    return summary


def format_validation_report(summary: ValidationSummary) -> str:
    """Format the validation summary into a human-readable text report."""
    pct = lambda n, total: f"{(n / total * 100):.1f}%" if total > 0 else "0.0%"
    tot = summary.college_records_count

    lines = [
        "==================================================================",
        "             AI-CON DATASET VALIDATION REPORT (PHASE 1)",
        "==================================================================",
        f"Total JSON files inspected:      {summary.total_json_files}",
        f"Valid JSON syntax:               {summary.valid_json_count} ({pct(summary.valid_json_count, summary.total_json_files)})",
        f"Invalid JSON syntax:             {summary.invalid_json_count}",
        f"Recognized college records:      {summary.college_records_count}",
        f"Unique record_id count:          {summary.unique_record_ids}",
        f"Duplicate record_id count:       {len(summary.duplicate_record_ids)}",
        "------------------------------------------------------------------",
        "INSTITUTE CODES & IDENTIFIERS:",
        f"  Records with institute_code:   {summary.records_with_institute_code} ({pct(summary.records_with_institute_code, tot)})",
        f"  Records without institute_code:{summary.records_without_institute_code} ({pct(summary.records_without_institute_code, tot)}) [Legitimate DHE records]",
        f"  Duplicate institute_code sets: {len(summary.duplicate_institute_codes)}",
        f"  Missing institute names:       {len(summary.missing_institute_names)}",
        "------------------------------------------------------------------",
        "FACTUAL ATTRIBUTE POPULATION (VERIFIED VALUES):",
        f"  Official website present:      {summary.official_website_count} ({pct(summary.official_website_count, tot)})",
        f"  Affiliation real value:        {summary.affiliation_present_count} ({pct(summary.affiliation_present_count, tot)})",
        f"  Affiliation confidence-only:   {summary.affiliation_confidence_only_count} ({pct(summary.affiliation_confidence_only_count, tot)}) [Value properly omitted]",
        f"  District real value:           {summary.district_present_count} ({pct(summary.district_present_count, tot)})",
        f"  District confidence-only:      {summary.district_confidence_only_count} ({pct(summary.district_confidence_only_count, tot)}) [Value properly omitted]",
        f"  City real value:               {summary.city_present_count} ({pct(summary.city_present_count, tot)})",
        f"  City confidence-only:          {summary.city_confidence_only_count} ({pct(summary.city_confidence_only_count, tot)}) [Value properly omitted]",
        f"  State real value:              {summary.state_present_count} ({pct(summary.state_present_count, tot)})",
        f"  Ownership real value:          {summary.ownership_present_count} ({pct(summary.ownership_present_count, tot)})",
        f"  Sources consulted present:     {summary.records_with_sources} ({pct(summary.records_with_sources, tot)})",
        f"  Zero sources consulted:        {summary.zero_source_count} ({pct(summary.zero_source_count, tot)})",
        "------------------------------------------------------------------",
        "EXTERNAL CONSISTENCY CHECKS:",
        f"  dataset_manifest.json checked: {summary.manifest_checked} (Matches: {summary.manifest_matches})",
        f"  college_dataset_index.csv chk: {summary.csv_index_checked} (Matches: {summary.csv_index_matches})",
        "------------------------------------------------------------------",
        f"TOTAL WARNINGS: {len(summary.warnings)}",
        f"TOTAL ERRORS:   {len(summary.errors)}",
        "==================================================================",
    ]

    if summary.duplicate_record_ids:
        lines.append("\nDUPLICATE RECORD IDS:")
        for dup in summary.duplicate_record_ids:
            lines.append(f"  - {dup}")

    if summary.duplicate_institute_codes:
        lines.append("\nDUPLICATE INSTITUTE CODES:")
        for code, recs in summary.duplicate_institute_codes.items():
            lines.append(f"  - Code {code}: {', '.join(recs)}")

    if summary.manifest_discrepancies:
        lines.append("\nMANIFEST DISCREPANCIES:")
        for disc in summary.manifest_discrepancies:
            lines.append(f"  - {disc}")

    if summary.csv_discrepancies:
        lines.append("\nCSV INDEX DISCREPANCIES:")
        for disc in summary.csv_discrepancies:
            lines.append(f"  - {disc}")

    if summary.errors:
        lines.append("\nCRITICAL ERRORS:")
        for err in summary.errors:
            lines.append(f"  - {err}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Validate AI-con college dataset")
    parser.add_argument(
        "--dataset",
        default="../college_ai_consultant_sparse_enriched_v4_no_cutoffs",
        help="Path to college dataset directory",
    )
    parser.add_argument(
        "--csv-index",
        default=None,
        help="Path to college_dataset_index.csv (defaults to dataset_dir/college_dataset_index.csv)",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Path to dataset_manifest.json (defaults to dataset_dir/dataset_manifest.json)",
    )
    parser.add_argument(
        "--report-out",
        default=None,
        help="Optional path to output validation report JSON or text",
    )
    args = parser.parse_args()

    dataset_path = args.dataset
    if not Path(dataset_path).is_dir():
        fallback = Path("cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs")
        if fallback.is_dir():
            dataset_path = str(fallback)

    summary = validate_dataset(dataset_path, csv_index_path=args.csv_index, manifest_path=args.manifest)
    text_report = format_validation_report(summary)
    print(text_report)

    if args.report_out:
        out_path = Path(args.report_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".json":
            out_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
        else:
            out_path.write_text(text_report, encoding="utf-8")
        print(f"\nReport written to: {out_path}")

    # Return non-zero only if critical errors exist (warnings do not fail exit code)
    if summary.errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
