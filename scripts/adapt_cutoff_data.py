"""
Deterministic Cutoff Data Adapter (AI-con Phase 3.1)
----------------------------------------------------
Adapts raw candidate MHT-CET CAP cutoff JSON files into the strict, canonical
hierarchical format accepted by CutoffAgent (<academic_year>/<institute_code>.json).

Features:
- Preserves all source fields without loss (rank, percentile, round, stage, list_type, source_file, page).
- Canonicalizes institute codes (e.g., 4-digit '1002' to 5-digit '01002' where appropriate).
- Maps institute codes against the verified college dataset index (college_dataset_index.csv).
- Retains source college names alongside canonical college names.
- Filters out empty scraper stubs (status: 'needs_url').
- Re-indexes into clean hierarchy: <out_dir>/<academic_year>/<institute_code>.json.
- Supports dry-run and validation-only modes.
- Generates detailed JSON and markdown adaptation audit reports.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Support direct and relative imports
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_cutoffs import CutoffValidator  # noqa: E402


def canonical_list_type(lt: Optional[str]) -> str:
    """Normalize list_type variants to canonical categories: 'CAP' or 'All India'."""
    if not lt:
        return "CAP"
    norm = lt.strip().lower().replace("_", " ").replace("-", " ")
    if norm in (
        "cap",
        "maharashtra minority",
        "maharashtra & minority seats",
        "state level",
        "home university",
        "other than home university",
        "state",
    ):
        return "CAP"
    if norm in ("all india", "ai", "jee", "jee main"):
        return "All India"
    return lt.strip()


STANDARD_BRANCHES: List[str] = [
    "Computer Engineering",
    "Computer Science and Engineering",
    "Information Technology",
    "Mechanical Engineering",
    "Civil Engineering",
    "Electrical Engineering",
    "Electronics and Telecommunication Engineering",
    "Electronics and Communication Engineering",
    "Electronics Engineering",
    "Chemical Engineering",
    "Instrumentation and Control Engineering",
    "Instrumentation Engineering",
    "Production Engineering",
    "Artificial Intelligence and Data Science",
    "Artificial Intelligence and Machine Learning",
    "Artificial Intelligence (AI) and Data Science",
    "Robotics and Automation",
    "Automobile Engineering",
    "Aeronautical Engineering",
    "Aerospace Engineering",
    "Agricultural Engineering",
    "Biomedical Engineering",
    "Biotechnology",
    "Bio Technology",
    "Food Technology",
    "Food Engineering and Technology",
    "Textile Engineering",
    "Textile Technology",
    "Mining Engineering",
    "Metallurgical Engineering",
    "Metallurgy and Material Technology",
    "Oil Technology",
    "Petro Chemical Engineering",
    "Petroleum Engineering",
    "Paint Technology",
    "Paints Technology",
    "Plastics and Polymer Engineering",
    "Plastic and Polymer Engineering",
    "Surface Coating Technology",
    "Paper and Pulp Technology",
    "Printing and Packing Technology",
    "Manufacturing Engineering",
    "Industrial Engineering",
    "Mechatronics Engineering",
    "Mechatronics",
    "Data Science",
    "Cyber Security",
    "Internet of Things (IoT)",
    "Computer Science and Business Systems",
    "Computer Science and Design",
    "Computer Science and Information Technology",
]

STANDARD_BRANCHES_BY_LEN: List[str] = sorted(STANDARD_BRANCHES, key=len, reverse=True)

MAHARASHTRA_CITIES_REGEX = (
    r"(?:Akola|Amravati|Pusad|Chikhali|Nagpur|Pune|Mumbai|Navi\s+Mumbai|Thane|Nashik|"
    r"Aurangabad|Chhatrapati\s+Sambhajinagar|Nanded|Yavatmal|Kolhapur|Sangli|Satara|"
    r"Solapur|Jalgaon|Dhule|Ahmednagar|Ratnagiri|Sindhudurg|Wardha|Bhandara|Gondia|"
    r"Chandrapur|Gadchiroli|Washim|Buldhana|Hingoli|Parbhani|Jalna|Beed|Latur|Osmanabad|Dharashiv)"
)

MIDDLE_SPLICE_PATTERN = re.compile(
    rf"\s*(?:"
        rf"(?:Institution|College|Campus)\s*\([^)]*\)"
        rf"|\([^)]*(?:Integrated\s+Campus|Campus|Autonomous|Institution|College)[^)]*\)"
        rf"|College\s+of\s+Engineering"
    rf")"
    rf"(?:\s*,\s*(?:{MAHARASHTRA_CITIES_REGEX}))?"
    rf"\s*",
    re.IGNORECASE,
)

SAFE_SUFFIX_PATTERN = re.compile(
    rf"^(?:[,:\-\|\/\s]\s*)"
    rf"(?:"
        rf"(?:(?:Government|Govt\.?|Autonomous|Integrated)\s+)?(?:Engineering\s+)?College(?:,\s*(?:{MAHARASHTRA_CITIES_REGEX}))?"
        rf"|Institute|Institution|Campus|\(Autonomous\)"
        rf"|{MAHARASHTRA_CITIES_REGEX}"
    rf")"
    rf"(?:\s*,\s*(?:{MAHARASHTRA_CITIES_REGEX}))?"
    rf"\s*$",
    re.IGNORECASE,
)

SAFE_TRAILING_SUFFIX_PATTERN = re.compile(
    rf"(?:[,:\-\|\/]\s*|\s+)"
    rf"(?:"
        rf"(?:(?:Government|Govt\.?|Autonomous|Integrated)\s+)?College(?:,\s*(?:{MAHARASHTRA_CITIES_REGEX}))?"
        rf"|Institute|Institution|Campus"
        rf"|{MAHARASHTRA_CITIES_REGEX}"
    rf")\s*$",
    re.IGNORECASE,
)


def clean_branch_name(raw_name: Any) -> str:
    """Deterministic branch name cleaner.

    Resolves extractor header splices without ever stripping valid branch words:
    - Spliced institution phrases: 'Computer Science and Institution(Integrated Campus), Amravati Engineering'
      -> 'Computer Science and Engineering'
    - Trailing college / city names: 'Chemical Engineering Akola' -> 'Chemical Engineering'
    - Trailing institute tags: 'Mechanical Engineering, Pusad' -> 'Mechanical Engineering'
    - Trailing college prefixes: 'Civil Engineering College, Chikhali' -> 'Civil Engineering'
    """
    if not raw_name or not isinstance(raw_name, str):
        return "Unknown Branch"

    text = re.sub(r"\s+", " ", raw_name).strip()
    if not text:
        return "Unknown Branch"

    # 1. Exact match check against standard branches
    for std in STANDARD_BRANCHES_BY_LEN:
        if text.lower() == std.lower():
            return std

    # 2. Check for spliced middle phrases (e.g. Institution(Integrated Campus), Amravati)
    text_middle_cleaned = MIDDLE_SPLICE_PATTERN.sub(" ", text)
    text_middle_cleaned = re.sub(r"\s+", " ", text_middle_cleaned).strip(" ,.-")

    for std in STANDARD_BRANCHES_BY_LEN:
        if text_middle_cleaned.lower() == std.lower():
            return std

    # 3. Match longest standard branch prefix followed by unambiguous suffix
    for cand in (text_middle_cleaned, text):
        cand_lower = cand.lower()
        for std in STANDARD_BRANCHES_BY_LEN:
            std_lower = std.lower()
            if cand_lower.startswith(std_lower):
                remainder = cand[len(std):]
                if not remainder.strip():
                    return std
                if SAFE_SUFFIX_PATTERN.match(remainder):
                    return std

    # 4. Fallback for non-standard branches: remove unambiguous trailing suffix
    fallback = text_middle_cleaned
    if SAFE_TRAILING_SUFFIX_PATTERN.search(fallback):
        fallback = SAFE_TRAILING_SUFFIX_PATTERN.sub("", fallback)

    fallback = re.sub(r"\s+", " ", fallback).strip(" ,.-")
    for std in STANDARD_BRANCHES_BY_LEN:
        if fallback.lower() == std.lower():
            return std

    return fallback if fallback else text


class CutoffAdapter:
    def __init__(
        self,
        college_index_csv: Optional[Path] = None,
        out_dir: Optional[Path] = None,
        dry_run: bool = False,
    ):
        self.out_dir = Path(out_dir) if out_dir else None
        self.dry_run = dry_run
        self.college_index: Dict[str, Dict[str, str]] = {}
        if college_index_csv and college_index_csv.is_file():
            self._load_college_index(college_index_csv)
        self.validator = CutoffValidator(college_index_csv=college_index_csv)

    def _load_college_index(self, csv_path: Path) -> None:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = (row.get("institute_code") or "").strip()
                if code:
                    self.college_index[code] = row
                    if len(code) == 4 and code.isdigit():
                        self.college_index[code.zfill(5)] = row

    def canonicalize_code(self, raw_code: Any) -> str:
        """Return standardized 5-digit string if 4 digits, otherwise stripped string."""
        s = str(raw_code).strip()
        if len(s) == 4 and s.isdigit():
            return s.zfill(5)
        return s

    def adapt_file(self, source_file: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        """Read and adapt a single cutoff JSON record.

        Returns:
            (adapted_dict, warnings) or (None, rejection_reasons)
        """
        rejections: List[str] = []
        try:
            content = source_file.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as exc:
            return None, [f"JSON decode failure: {exc}"]

        if not isinstance(data, dict):
            return None, ["Root is not a JSON object"]

        # Check for empty crawler stubs
        if data.get("status") == "needs_url" or (data.get("extracted") is None and not data.get("branches")):
            return None, ["Skipping scraper crawler stub (no extracted cutoffs)"]

        raw_code = data.get("institute_code")
        if not raw_code:
            return None, ["Missing institute_code"]

        code_canonical = self.canonicalize_code(raw_code)
        ay = data.get("academic_year")
        if not ay:
            return None, ["Missing academic_year"]

        branches_in = data.get("branches")
        if not isinstance(branches_in, list) or not branches_in:
            return None, ["Missing or empty branches list"]

        # Map canonical institute name if available
        src_name = data.get("institute_name") or ""
        canonical_name = src_name
        if code_canonical in self.college_index:
            canonical_name = self.college_index[code_canonical].get("institute_name") or src_name

        adapted_branches: List[Dict[str, Any]] = []
        warnings: List[str] = []
        total_cutoffs_kept = 0
        file_seen_evidence_ids: Set[str] = set()

        root_source_file = data.get("source_file") or (data.get("source_files", [None])[0] if isinstance(data.get("source_files"), list) and data.get("source_files") else None)

        for b in branches_in:
            if not isinstance(b, dict):
                continue
            raw_b_name = b.get("branch") or b.get("course_name") or "Unknown Branch"
            b_name = clean_branch_name(raw_b_name)
            course_code = b.get("course_code")

            adapted_categories: List[Dict[str, Any]] = []
            for cat in b.get("categories", []):
                if not isinstance(cat, dict):
                    continue
                cat_token = cat.get("category")
                if not cat_token:
                    continue

                cat_meaning = cat.get("category_meaning")
                cat_meaning_conf = cat.get("category_meaning_confidence")

                valid_cutoffs: List[Dict[str, Any]] = []
                cat_seen_cutoffs: Set[Tuple[int, str, str, str]] = set()

                for cut in cat.get("cutoffs", []):
                    if not isinstance(cut, dict):
                        continue

                    # Safely validate positive integer closing_rank
                    c_rank_raw = cut.get("closing_rank")
                    if c_rank_raw is None or str(c_rank_raw).strip() in ("", "None", "null", "N/A"):
                        continue
                    try:
                        c_rank = int(str(c_rank_raw).strip())
                        if c_rank <= 0:
                            continue
                    except (ValueError, TypeError):
                        continue

                    # Safely validate float closing_percentile in [0.0, 100.0]
                    c_perc = None
                    if cut.get("closing_percentile") is not None:
                        try:
                            p_str = str(cut["closing_percentile"]).strip()
                            if p_str not in ("", "None", "null", "N/A"):
                                p_val = float(p_str)
                                if 0.0 <= p_val <= 100.0:
                                    c_perc = round(p_val, 7)
                        except (ValueError, TypeError):
                            c_perc = None

                    round_val = cut.get("round", 1)
                    if not isinstance(round_val, int) or round_val not in (1, 2, 3, 4):
                        try:
                            round_val = int(str(round_val).strip())
                        except (ValueError, TypeError):
                            round_val = 1

                    stage_str = str(cut.get("stage", "1")).strip()
                    list_type_str = str(cut.get("list_type", "CAP")).strip()
                    c_list_type = canonical_list_type(list_type_str)
                    level_key_str = str(cut.get("level_key") or "").strip().upper()

                    # Deduplicate exact duplicate category/round/level entries within branch
                    cut_key = (round_val, stage_str.upper(), c_list_type.upper(), level_key_str)
                    if cut_key in cat_seen_cutoffs:
                        continue
                    cat_seen_cutoffs.add(cut_key)

                    # Construct or preserve unique deterministic evidence_id
                    orig_ev_id = cut.get("evidence_id")
                    source_ev_id: Optional[str] = None
                    if not orig_ev_id:
                        branch_slug = str(course_code) if course_code else re.sub(r"[^A-Za-z0-9]", "", b_name)[:6].upper()
                        cat_clean = re.sub(r"[^A-Za-z0-9]", "", str(cat_token)).upper()
                        ev_id = f"EV-{code_canonical}-{branch_slug}-{cat_clean}-R{round_val}"
                        if stage_str not in ("1", "I", "CAP"):
                            ev_id += f"-S{stage_str}"
                    else:
                        raw_s = str(orig_ev_id).strip()
                        norm = raw_s
                        # Normalize EV-1002-... to EV-01002-...
                        norm = re.sub(r"^EV-(\d{4})-", r"EV-0\1-", norm)
                        # Normalize colon format: 2020-21:1002:... to 2020-21:01002:...
                        norm = re.sub(r"^(\d{4}-\d{2}):(\d{4}):", r"\1:0\2:", norm)
                        # Normalize 9-digit course code in colon format: ...:100224210:... to ...:0100224210:...
                        norm = re.sub(r"^(\d{4}-\d{2}:\d{5}):(\d{9}):", r"\1:0\2:", norm)
                        norm = re.sub(r"^(\d{4}-\d{2}):(\d{4}):(\d{9}):", r"\1:0\2:0\3:", norm)
                        ev_id = norm
                        if norm != raw_s:
                            source_ev_id = raw_s

                    # Ensure evidence_id is globally unique within this file
                    base_ev_id = str(ev_id)
                    disambig = 1
                    while ev_id in file_seen_evidence_ids:
                        ev_id = f"{base_ev_id}-{disambig}"
                        disambig += 1
                    file_seen_evidence_ids.add(ev_id)

                    src_file_final = cut.get("source_file") or root_source_file

                    cutoff_entry: Dict[str, Any] = {
                        "round": round_val,
                        "stage": stage_str,
                        "list_type": c_list_type,
                        "closing_rank": c_rank,
                        "closing_percentile": c_perc,
                        "evidence_id": ev_id,
                    }
                    if c_list_type != list_type_str:
                        cutoff_entry["source_list_type"] = list_type_str
                    if source_ev_id:
                        cutoff_entry["source_evidence_id"] = source_ev_id
                    elif cut.get("source_evidence_id"):
                        cutoff_entry["source_evidence_id"] = cut["source_evidence_id"]

                    if src_file_final:
                        cutoff_entry["source_file"] = src_file_final
                    if cut.get("page") is not None:
                        cutoff_entry["page"] = cut["page"]

                    # Preserve extended audit fields if present
                    for extra in ("level_key", "level_label"):
                        if extra in cut:
                            cutoff_entry[extra] = cut[extra]

                    valid_cutoffs.append(cutoff_entry)
                    total_cutoffs_kept += 1

                if valid_cutoffs:
                    adapted_categories.append({
                        "category": str(cat_token).strip(),
                        "category_meaning": cat_meaning,
                        "category_meaning_confidence": cat_meaning_conf,
                        "cutoffs": valid_cutoffs,
                    })

            if adapted_categories:
                b_dict: Dict[str, Any] = {
                    "branch": b_name,
                    "categories": adapted_categories,
                }
                if b_name != raw_b_name:
                    b_dict["source_branch_name"] = raw_b_name
                if course_code:
                    b_dict["course_code"] = str(course_code)
                adapted_branches.append(b_dict)

        if not adapted_branches or total_cutoffs_kept == 0:
            return None, ["No valid cutoff figures found across branches"]

        adapted_record: Dict[str, Any] = {
            "institute_code": code_canonical,
            "institute_name": canonical_name,
            "source_institute_name": src_name if src_name != canonical_name else None,
            "academic_year": ay.strip(),
            "branches": adapted_branches,
        }

        # Preserve top-level source metadata
        for top_meta in ("home_university", "status", "source_files"):
            if top_meta in data:
                adapted_record[top_meta] = data[top_meta]

        return adapted_record, warnings

    def adapt_directory(
        self,
        source_dir: Path,
        out_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Process an entire directory tree of source cutoff files."""
        target_out = Path(out_dir) if out_dir else self.out_dir
        if not target_out and not self.dry_run:
            raise ValueError("out_dir must be specified when dry_run=False")

        report: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_directory": str(source_dir),
            "output_directory": str(target_out) if target_out else "DRY_RUN",
            "files_scanned": 0,
            "records_adapted": 0,
            "records_skipped": 0,
            "cutoffs_generated": 0,
            "academic_years": {},
            "institutes": {},
            "skipped_details": [],
            "warnings": [],
        }

        # Collect source JSON files
        source_files = sorted(source_dir.rglob("*.json"))
        report["files_scanned"] = len(source_files)

        for src in source_files:
            if src.name.startswith("_") or src.name in ("manifest.json", "schema.json"):
                continue

            adapted, msgs = self.adapt_file(src)
            if adapted is None:
                report["records_skipped"] += 1
                report["skipped_details"].append({"file": src.name, "reasons": msgs})
                continue

            ay = adapted["academic_year"]
            code = adapted["institute_code"]

            # Count cutoffs
            cut_count = sum(
                len(c.get("cutoffs", []))
                for b in adapted.get("branches", [])
                for c in b.get("categories", [])
            )
            report["records_adapted"] += 1
            report["cutoffs_generated"] += cut_count
            report["academic_years"][ay] = report["academic_years"].get(ay, 0) + cut_count
            report["institutes"][code] = report["institutes"].get(code, 0) + cut_count

            # Write adapted file if not dry run
            if not self.dry_run and target_out:
                dest_year_dir = target_out / ay
                dest_year_dir.mkdir(parents=True, exist_ok=True)
                dest_file = dest_year_dir / f"{code}.json"
                dest_file.write_text(json.dumps(adapted, indent=2, ensure_ascii=False), encoding="utf-8")

        return report


def adapt_raw_file(
    source_file: Union[str, Path],
    college_index_csv: Optional[Union[str, Path]] = None,
    canonical_names: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Convenience helper to adapt a single raw JSON file."""
    src_p = Path(source_file)
    csv_p = Path(college_index_csv) if college_index_csv else None
    adapter = CutoffAdapter(college_index_csv=csv_p)
    if canonical_names:
        for k, v in canonical_names.items():
            adapter.college_index[k] = {"institute_name": v}
            if len(k) == 4 and k.isdigit():
                adapter.college_index[k.zfill(5)] = {"institute_name": v}
    adapted, _ = adapter.adapt_file(src_p)
    return adapted


def main():
    ap = argparse.ArgumentParser(description="AI-con Phase 3 Cutoff Data Adapter")
    ap.add_argument(
        "--source", "--raw-dir", "-s",
        dest="source",
        required=True,
        help="Path to raw cutoff folder (e.g. cutoffs/raw_extracted)",
    )
    ap.add_argument(
        "--out", "--out-dir", "-o",
        dest="out",
        default=None,
        help="Destination directory (e.g. cutoffs/adapted_staging)",
    )
    ap.add_argument(
        "--college-index", "--index-csv", "-c",
        dest="college_index",
        default="../college_ai_consultant_sparse_enriched_v4_no_cutoffs/college_dataset_index.csv",
        help="Path to college dataset index CSV for institute mapping",
    )
    ap.add_argument(
        "--report-out", "--report", "-r",
        dest="report_out",
        default=None,
        help="Optional destination path for JSON adaptation report",
    )
    ap.add_argument("--dry-run", action="store_true", help="Validate and report without writing files")
    args = ap.parse_args()

    src_path = Path(args.source)
    if not src_path.is_dir():
        print(f"Error: Source directory not found: {src_path}", file=sys.stderr)
        sys.exit(1)

    csv_path = Path(args.college_index).resolve()
    adapter = CutoffAdapter(
        college_index_csv=csv_path if csv_path.is_file() else None,
        out_dir=Path(args.out) if args.out else None,
        dry_run=args.dry_run,
    )

    print(f"Adapting cutoffs from: {src_path}")
    report = adapter.adapt_directory(src_path)
    print(f"Scanned: {report['files_scanned']} files")
    print(f"Adapted: {report['records_adapted']} college records")
    print(f"Skipped: {report['records_skipped']} files (e.g. crawler stubs)")
    print(f"Total Cutoffs Ingested: {report['cutoffs_generated']}")
    print("Breakdown by Academic Year:", report["academic_years"])

    if args.report_out:
        rep_file = Path(args.report_out)
        rep_file.parent.mkdir(parents=True, exist_ok=True)
        rep_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to: {rep_file}")
    elif args.out and not args.dry_run:
        rep_dir = Path(args.out).parent / "reports"
        rep_dir.mkdir(parents=True, exist_ok=True)
        rep_file = rep_dir / f"adaptation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        rep_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to: {rep_file}")


if __name__ == "__main__":
    main()
