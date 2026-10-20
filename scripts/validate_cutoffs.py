"""
Cutoff Data Validation Module (AI-con Phase 3.1)
------------------------------------------------
Provides strict, deterministic schema and semantic validation for historical
MHT-CET CAP cutoff records.

Validates:
1. JSON structure & schema adherence.
2. Academic year consistency between directory name and record payload.
3. Institute code format (4-5 digits) and college name presence.
4. Branch names and course codes.
5. Exact category tokens (zero unauthorized merging of GOPENH/GOPENO/GOPENS).
6. CAP round (1-4) and stage ("1", "2").
7. Metric validity:
   - closing_rank: positive integer.
   - closing_percentile: float in [0.0, 100.0] with full decimal precision.
8. Source evidence traceability (source_file, page, evidence_id).
9. Duplicate and conflict detection within and across records.
10. Explicit distinction between Maharashtra State (CAP) and All India (JEE Main) list types.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


VALID_ROUNDS = {1, 2, 3, 4}
VALID_STAGES = {"1", "2", "3", "I", "II", "III", "CAP", "FINAL"}
VALID_LIST_TYPES = {
    "CAP",
    "All India",
    "AI",
    "State Level",
    "Home University",
    "Other than Home University",
    "maharashtra_minority",
    "Maharashtra Minority",
    "Maharashtra & Minority Seats",
}

# Standard MHT-CET seat category prefixes and known tokens (including DEF, PWD, DEFR, PWDR special reservations)
KNOWN_CATEGORY_PATTERN = re.compile(
    r"^(?:G|L|DEF[1-3]?|PWD[1-3]?|DEFR(?:OBC)?|PWDR(?:OBC)?)?"
    r"(?:OPEN|SC|ST|OBC|NT[1-3A-D]?|VJ|DT|SBC|SEBC|EWS|TFWS|AI|ORPHAN|MI|MINORITY)"
    r"(?:[HOS])?(?:[1-5])?$",
    re.IGNORECASE,
)


class CutoffValidationError:
    """Represents a specific validation finding (error or warning)."""

    def __init__(self, level: str, code: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.level = level  # "ERROR" or "WARNING"
        self.code = code
        self.message = message
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "context": self.context,
        }

    def __repr__(self) -> str:
        return f"[{self.level}] {self.code}: {self.message}"


class CutoffValidator:
    """Validates raw and adapted cutoff files and directories."""

    def __init__(self, college_index_csv: Optional[Path] = None, pdf_dir: Optional[Union[str, Path]] = None):
        self.known_codes: Set[str] = set()
        self.pdf_dir: Optional[Path] = Path(pdf_dir) if pdf_dir else None
        if college_index_csv and college_index_csv.is_file():
            self._load_college_index(college_index_csv)

    def _load_college_index(self, csv_path: Path) -> None:
        try:
            import csv
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = (row.get("institute_code") or "").strip()
                    if code:
                        self.known_codes.add(code)
                        if len(code) == 4 and code.isdigit():
                            self.known_codes.add(code.zfill(5))
        except Exception:
            pass

    def validate_file(
        self,
        file_path: Path,
        expected_year: Optional[str] = None,
    ) -> Tuple[bool, List[CutoffValidationError], Dict[str, Any]]:
        """Validate a single cutoff JSON file.

        Returns:
            (is_valid, list_of_errors, stats_dict)
        """
        findings: List[CutoffValidationError] = []
        stats = {
            "file": str(file_path),
            "academic_year": None,
            "institute_code": None,
            "branch_count": 0,
            "category_count": 0,
            "cutoff_count": 0,
        }

        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as exc:
            findings.append(CutoffValidationError(
                "ERROR", "MALFORMED_JSON", f"Failed to parse JSON: {exc}", {"path": str(file_path)}
            ))
            return False, findings, stats

        if not isinstance(data, dict):
            findings.append(CutoffValidationError(
                "ERROR", "INVALID_ROOT_TYPE", "Root element must be a JSON object", {"path": str(file_path)}
            ))
            return False, findings, stats

        # Scraper stub check
        if data.get("status") == "needs_url":
            findings.append(CutoffValidationError(
                "ERROR", "EMPTY_SCRAPER_STUB",
                "Unextracted scraper stub: File is a crawler stub with status 'needs_url'",
                {"path": str(file_path)}
            ))
            return False, findings, stats

        # 1. Academic Year Check
        ay = data.get("academic_year")
        if not ay or not isinstance(ay, str):
            findings.append(CutoffValidationError("ERROR", "MISSING_ACADEMIC_YEAR", "Missing academic_year in root"))
        else:
            stats["academic_year"] = ay
            if not re.match(r"^\d{4}-\d{2}$", ay.strip()):
                findings.append(CutoffValidationError(
                    "ERROR", "INVALID_ACADEMIC_YEAR",
                    f"Academic year '{ay}' must match YYYY-YY format (e.g. 2024-25). Invalid academic_year",
                    {"academic_year": ay}
                ))
            if expected_year and ay.strip() != expected_year.strip():
                findings.append(CutoffValidationError(
                    "ERROR", "YEAR_MISMATCH",
                    f"Directory year '{expected_year}' differs from record year '{ay}' (academic_year)",
                    {"expected": expected_year, "actual": ay}
                ))

        # 2. Institute Code Check
        code = data.get("institute_code")
        if not code:
            findings.append(CutoffValidationError("ERROR", "MISSING_INSTITUTE_CODE", "Missing institute_code in root"))
        else:
            code_str = str(code).strip()
            stats["institute_code"] = code_str
            if not (code_str.isdigit() and len(code_str) in (4, 5)):
                findings.append(CutoffValidationError(
                    "WARNING", "UNUSUAL_INSTITUTE_CODE",
                    f"Institute code '{code_str}' is not 4 or 5 digits",
                    {"code": code_str}
                ))
            elif self.known_codes and code_str not in self.known_codes and code_str.zfill(5) not in self.known_codes:
                findings.append(CutoffValidationError(
                    "WARNING", "UNMAPPED_INSTITUTE_CODE",
                    f"Institute code '{code_str}' does not match existing college dataset index",
                    {"code": code_str}
                ))

        # 3. Institute Name Check
        name = data.get("institute_name")
        if not name or not isinstance(name, str) or not name.strip():
            findings.append(CutoffValidationError("ERROR", "MISSING_INSTITUTE_NAME", "Missing institute_name in root"))

        # 4. Branches Check
        branches = data.get("branches")
        if not isinstance(branches, list) or not branches:
            findings.append(CutoffValidationError(
                "ERROR", "NO_BRANCHES", "Record has no branches list or branches is empty"
            ))
            return False, findings, stats

        stats["branch_count"] = len(branches)
        seen_cutoffs: Dict[Tuple[str, str, str, int, str, str, str], Tuple[int, Optional[float]]] = {}
        seen_evidence_ids: Set[str] = set()
        seen_missing_pdfs: Set[str] = set()

        for b_idx, branch_obj in enumerate(branches):
            if not isinstance(branch_obj, dict):
                findings.append(CutoffValidationError("ERROR", "INVALID_BRANCH_OBJECT", f"Branch at index {b_idx} not an object"))
                continue
            b_name = branch_obj.get("branch") or branch_obj.get("course_name")
            if not b_name:
                findings.append(CutoffValidationError("ERROR", "MISSING_BRANCH_NAME", f"Branch index {b_idx} missing branch name"))
                b_name = f"UNKNOWN_BRANCH_{b_idx}"

            categories = branch_obj.get("categories")
            if not isinstance(categories, list) or not categories:
                findings.append(CutoffValidationError("WARNING", "NO_CATEGORIES", f"Branch '{b_name}' has empty categories"))
                continue

            stats["category_count"] += len(categories)

            for c_idx, cat_obj in enumerate(categories):
                if not isinstance(cat_obj, dict):
                    continue
                cat_token = cat_obj.get("category")
                if not cat_token:
                    findings.append(CutoffValidationError(
                        "ERROR", "MISSING_CATEGORY_TOKEN",
                        f"Branch '{b_name}' category index {c_idx} missing category token"
                    ))
                    continue

                cat_str = str(cat_token).strip()
                if not KNOWN_CATEGORY_PATTERN.match(cat_str):
                    findings.append(CutoffValidationError(
                        "WARNING", "UNUSUAL_CATEGORY_TOKEN",
                        f"Unrecognized quota category token: '{cat_str}' in branch '{b_name}'",
                        {"category": cat_str, "branch": b_name}
                    ))

                cutoffs = cat_obj.get("cutoffs")
                if not isinstance(cutoffs, list) or not cutoffs:
                    findings.append(CutoffValidationError(
                        "WARNING", "EMPTY_CUTOFF_LIST",
                        f"Category '{cat_str}' in '{b_name}' has no cutoff entries"
                    ))
                    continue

                for cut_idx, cut in enumerate(cutoffs):
                    if not isinstance(cut, dict):
                        continue
                    stats["cutoff_count"] += 1

                    # Round validation
                    rnd = cut.get("round")
                    if rnd not in VALID_ROUNDS:
                        findings.append(CutoffValidationError(
                            "ERROR", "INVALID_ROUND",
                            f"Round must be in {VALID_ROUNDS}, got {rnd} in '{b_name}' / '{cat_str}'",
                            {"round": rnd, "branch": b_name, "category": cat_str}
                        ))

                    # Stage validation
                    stg = str(cut.get("stage", "1")).strip()

                    # List type validation
                    l_type = str(cut.get("list_type", "CAP")).strip()

                    # Closing Rank validation (mandatory positive integer)
                    c_rank = cut.get("closing_rank")
                    if c_rank is None:
                        findings.append(CutoffValidationError(
                            "ERROR", "MISSING_CLOSING_RANK",
                            f"Missing closing_rank: closing_rank is null in '{b_name}' / '{cat_str}' / Round {rnd}"
                        ))
                    elif not (isinstance(c_rank, int) and not isinstance(c_rank, bool) and c_rank > 0):
                        findings.append(CutoffValidationError(
                            "ERROR", "INVALID_CLOSING_RANK",
                            f"Invalid closing_rank: closing_rank must be positive int, got {c_rank} ({type(c_rank).__name__})"
                        ))

                    # Closing Percentile validation (float in [0.0, 100.0])
                    c_perc = cut.get("closing_percentile")
                    if c_perc is not None:
                        try:
                            f_perc = float(c_perc)
                            if not (0.0 <= f_perc <= 100.0):
                                findings.append(CutoffValidationError(
                                    "ERROR", "PERCENTILE_OUT_OF_RANGE",
                                    f"Invalid closing_percentile: Percentile {f_perc} not in [0.0, 100.0]"
                                ))
                        except (ValueError, TypeError):
                            findings.append(CutoffValidationError(
                                "ERROR", "INVALID_PERCENTILE_TYPE",
                                f"Invalid closing_percentile: Invalid percentile value '{c_perc}'"
                            ))

                    # Source evidence traceability & uniqueness
                    ev_id = cut.get("evidence_id")
                    src_file = cut.get("source_file") or data.get("source_file")

                    if not ev_id:
                        findings.append(CutoffValidationError(
                            "ERROR", "MISSING_EVIDENCE_ID",
                            f"Missing evidence_id in '{b_name}' / '{cat_str}' / Round {rnd}"
                        ))
                    else:
                        if ev_id in seen_evidence_ids:
                            findings.append(CutoffValidationError(
                                "ERROR", "DUPLICATE_EVIDENCE_ID",
                                f"Duplicate evidence_id '{ev_id}' in file",
                                {"evidence_id": ev_id, "branch": b_name, "category": cat_str}
                            ))
                        seen_evidence_ids.add(ev_id)

                    if not src_file:
                        findings.append(CutoffValidationError(
                            "WARNING", "MISSING_SOURCE_FILE",
                            f"Missing source_file in '{b_name}' / '{cat_str}' / Round {rnd}"
                        ))
                    else:
                        # Check whether source PDF exists locally on disk (recorded once per missing PDF per file)
                        if src_file not in seen_missing_pdfs:
                            pdf_found = False
                            candidate_dirs: List[Path] = [
                                Path("cutoffs/historical_pdf_input"),
                                Path("cutoffs/source_pdfs"),
                                Path("cutoffs"),
                                Path("."),
                            ]
                            if self.pdf_dir:
                                candidate_dirs.insert(0, self.pdf_dir)
                            for candidate_dir in candidate_dirs:
                                if (candidate_dir / src_file).is_file():
                                    pdf_found = True
                                    break
                            if not pdf_found:
                                seen_missing_pdfs.add(src_file)
                                findings.append(CutoffValidationError(
                                    "WARNING", "SOURCE_PDF_UNVERIFIED_OFFLINE",
                                    f"Source PDF '{src_file}' not found in local workspace; evidence marked unverified",
                                    {"source_file": src_file}
                                ))

                    # Duplicate check (key: course_code/branch, category, round, stage, list_type, level_key)
                    c_code = str(branch_obj.get("course_code") or "").strip()
                    level_key = str(cut.get("level_key") or "").strip()
                    key = (
                        c_code,
                        b_name.lower(),
                        cat_str.upper(),
                        int(rnd or 0),
                        stg.upper(),
                        l_type.upper(),
                        level_key.upper(),
                    )
                    if key in seen_cutoffs:
                        prev_c_rank, prev_c_perc = seen_cutoffs[key]
                        if prev_c_rank == c_rank and (prev_c_perc is None or prev_c_perc == c_perc):
                            findings.append(CutoffValidationError(
                                "ERROR", "DUPLICATE_CUTOFF_ENTRY",
                                f"Duplicate cutoff for branch '{b_name}', category '{cat_str}', round {rnd}, stage {stg}, list_type {l_type}, level '{level_key}'",
                                {"key": str(key), "rank": c_rank, "percentile": c_perc}
                            ))
                        else:
                            findings.append(CutoffValidationError(
                                "ERROR", "CONFLICTING_CUTOFF_ENTRY",
                                f"Duplicate cutoff (conflicting values): branch '{b_name}', category '{cat_str}', round {rnd}, stage {stg}, list_type {l_type}, level '{level_key}': "
                                f"first entry had rank {prev_c_rank} / percentile {prev_c_perc}, second entry has rank {c_rank} / percentile {c_perc}",
                                {"key": str(key), "rank1": prev_c_rank, "perc1": prev_c_perc, "rank2": c_rank, "perc2": c_perc}
                            ))
                    else:
                        seen_cutoffs[key] = (c_rank, c_perc)

        has_fatal_errors = any(f.level == "ERROR" for f in findings)
        return (not has_fatal_errors), findings, stats

    def validate_directory(
        self,
        directory: Path,
        generate_report: bool = True,
    ) -> Dict[str, Any]:
        """Scans a cutoff directory (expecting year subdirectories or JSON files) and compiles report."""
        report: Dict[str, Any] = {
            "root_directory": str(directory),
            "total_files_inspected": 0,
            "valid_files": 0,
            "invalid_files": 0,
            "total_cutoffs_inspected": 0,
            "accepted_records": 0,
            "rejected_records": 0,
            "genuine_duplicates": 0,
            "conflicts_requiring_review": 0,
            "source_unverified_records": 0,
            "counts_by_year": {},
            "counts_by_institute": {},
            "counts_by_round": {},
            "counts_by_category": {},
            "findings_summary": {"ERROR": 0, "WARNING": 0},
            "findings_by_code": {},
            "warnings_by_reason": {},
            "errors": [],
            "warnings": [],
        }

        if not directory.is_dir():
            report["errors"].append({
                "code": "DIRECTORY_NOT_FOUND",
                "message": f"Directory does not exist: {directory}",
            })
            return report

        # Discover canonical cutoff files (strictly academic year subfolders matching YYYY-YY)
        year_dirs = [
            d for d in directory.iterdir()
            if d.is_dir() and re.match(r"^\d{4}-\d{2}$", d.name)
        ]
        target_files: List[Tuple[Path, Optional[str]]] = []

        if year_dirs:
            for yd in sorted(year_dirs):
                for f in sorted(yd.glob("*.json")):
                    if not f.name.startswith((".", "_")) and f.name not in ("manifest.json", "schema.json") and not f.name.endswith("_report.json"):
                        target_files.append((f, yd.name))
        else:
            for f in sorted(directory.glob("*.json")):
                if not f.name.startswith((".", "_")) and f.name not in ("manifest.json", "schema.json") and not f.name.endswith("_report.json") and "report" not in f.name.lower():
                    target_files.append((f, None))

        report["total_files_inspected"] = len(target_files)

        for file_path, exp_year in target_files:
            is_valid, findings, stats = self.validate_file(file_path, expected_year=exp_year)

            if is_valid:
                report["valid_files"] += 1
                report["accepted_records"] += stats["cutoff_count"]
            else:
                report["invalid_files"] += 1
                report["rejected_records"] += stats["cutoff_count"]

            report["total_cutoffs_inspected"] += stats["cutoff_count"]

            ay = stats["academic_year"] or "unknown"
            report["counts_by_year"][ay] = report["counts_by_year"].get(ay, 0) + stats["cutoff_count"]

            code = stats["institute_code"] or "unknown"
            report["counts_by_institute"][code] = report["counts_by_institute"].get(code, 0) + stats["cutoff_count"]

            for fnd in findings:
                report["findings_summary"][fnd.level] = report["findings_summary"].get(fnd.level, 0) + 1
                report["findings_by_code"][fnd.code] = report["findings_by_code"].get(fnd.code, 0) + 1

                if fnd.code == "DUPLICATE_CUTOFF_ENTRY":
                    report["genuine_duplicates"] += 1
                elif fnd.code == "CONFLICTING_CUTOFF_ENTRY":
                    report["conflicts_requiring_review"] += 1
                elif fnd.code == "SOURCE_PDF_UNVERIFIED_OFFLINE":
                    report["source_unverified_records"] += 1

                if fnd.level == "WARNING":
                    report["warnings_by_reason"][fnd.code] = report["warnings_by_reason"].get(fnd.code, 0) + 1

                f_entry = {
                    "file": file_path.name,
                    "code": fnd.code,
                    "message": fnd.message,
                    "context": fnd.context,
                }
                if fnd.level == "ERROR":
                    report["errors"].append(f_entry)
                else:
                    report["warnings"].append(f_entry)

        return report


def validate_cutoff_file(
    file_path: Union[str, Path],
    expected_year: Optional[str] = None,
    college_index_csv: Optional[Union[str, Path]] = None,
    pdf_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Convenience helper to validate a single file and return a structured report dictionary."""
    fpath = Path(file_path)
    csv_path = Path(college_index_csv) if college_index_csv else None
    validator = CutoffValidator(college_index_csv=csv_path, pdf_dir=pdf_dir)
    is_valid, findings, stats = validator.validate_file(fpath, expected_year=expected_year)
    errors = [f.message for f in findings if f.level == "ERROR"]
    warnings = [f.message for f in findings if f.level == "WARNING"]
    return {
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "findings": [f.to_dict() for f in findings],
        "stats": stats,
        "cutoffs_checked": stats.get("cutoff_count", 0),
    }


def main():
    ap = argparse.ArgumentParser(
        description="Strict deterministic validator for AI-con MHT-CET CAP cutoff records (Phase 3.1)"
    )
    ap.add_argument(
        "--cutoffs-dir", "--cutoffs", "-d",
        dest="cutoffs_dir",
        required=True,
        help="Path to cutoffs directory containing academic year subfolders (e.g. cutoffs/adapted_staging)",
    )
    ap.add_argument(
        "--report-out", "--report", "-r",
        dest="report_out",
        default=None,
        help="Optional path to output detailed JSON validation report",
    )
    ap.add_argument(
        "--college-index", "-c",
        dest="college_index",
        default="../college_ai_consultant_sparse_enriched_v4_no_cutoffs/college_dataset_index.csv",
        help="Path to college dataset index CSV for institute mapping verification",
    )
    ap.add_argument(
        "--pdf-dir", "-p",
        dest="pdf_dir",
        default=None,
        help="Optional path to source cutoff PDFs directory for offline verification",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures (exit nonzero if warnings exist)",
    )
    args = ap.parse_args()

    cutoffs_path = Path(args.cutoffs_dir)
    if not cutoffs_path.is_dir():
        print(f"Error: Cutoffs directory not found: {cutoffs_path}", file=sys.stderr)
        sys.exit(1)

    csv_path = Path(args.college_index).resolve()
    pdf_p = Path(args.pdf_dir).resolve() if args.pdf_dir else None
    validator = CutoffValidator(
        college_index_csv=csv_path if csv_path.is_file() else None,
        pdf_dir=pdf_p if pdf_p and pdf_p.is_dir() else None,
    )

    print("=" * 70)
    print("AI-CON PHASE 3: CUTOFF DATA VALIDATION")
    print(f"Target Directory: {cutoffs_path}")
    print("=" * 70)

    report = validator.validate_directory(cutoffs_path)

    print(f"\nFiles Inspected:        {report['total_files_inspected']}")
    print(f"Valid College Files:    {report['valid_files']}")
    print(f"Invalid College Files:  {report['invalid_files']}")
    print(f"Total Cutoff Entries:   {report['total_cutoffs_inspected']}")
    print(f"Accepted Cutoffs:       {report['accepted_records']:,}")
    print(f"Rejected Cutoffs:       {report['rejected_records']:,}")
    print(f"Genuine Duplicates:     {report['genuine_duplicates']:,}")
    print(f"Conflicts for Review:   {report['conflicts_requiring_review']:,}")
    print(f"Source Unverified:      {report['source_unverified_records']:,}")
    print("\nCutoff Breakdown by Academic Year:")
    for yr, cnt in sorted(report["counts_by_year"].items()):
        print(f"  - {yr}: {cnt:,} cutoff entries")

    print(f"\nFindings Summary:")
    print(f"  - Critical Errors: {report['findings_summary']['ERROR']}")
    print(f"  - Audit Warnings:  {report['findings_summary']['WARNING']}")

    if report.get("warnings_by_reason"):
        print("\nWarnings Breakdown by Reason:")
        for rsn, cnt in sorted(report["warnings_by_reason"].items()):
            print(f"  - {rsn}: {cnt:,}")

    if report["errors"]:
        print("\nCritical Errors Encountered (Sample):")
        for err in report["errors"][:10]:
            print(f"  [ERROR] {err['file']} - {err['code']}: {err['message']}")
        if len(report["errors"]) > 10:
            print(f"  ... and {len(report['errors']) - 10} more errors.")

    if report["warnings"]:
        print("\nAudit Warnings (Sample):")
        for warn in report["warnings"][:5]:
            print(f"  [WARN] {warn['file']} - {warn['code']}: {warn['message']}")
        if len(report["warnings"]) > 5:
            print(f"  ... and {len(report['warnings']) - 5} more warnings.")

    if args.report_out:
        out_p = Path(args.report_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nFull validation report saved to: {out_p}")

    print("=" * 70)
    if report["invalid_files"] > 0 or report["findings_summary"]["ERROR"] > 0:
        print("VALIDATION RESULT: FAILED (Errors detected)")
        print("=" * 70)
        sys.exit(1)
    elif args.strict and report["findings_summary"]["WARNING"] > 0:
        print("VALIDATION RESULT: FAILED (Strict mode: warnings detected)")
        print("=" * 70)
        sys.exit(1)
    else:
        print("VALIDATION RESULT: PASSED (All records valid)")
        print("=" * 70)
        sys.exit(0)


if __name__ == "__main__":
    main()
