"""
Multi-Year Cutoff Reconciliation Engine (AI-con Phase 3)
--------------------------------------------------------
Deterministically merges and reconciles historical adapted cutoff staging records
(e.g., 2020-21, 2021-22, 2022-23) with current-year adapted staging records
(2023-24, 2024-25, 2025-26) into a single, clean chronological staging dataset:

  cutoffs/phase3_final_staging/<academic_year>/<institute_code>.json

Reconciliation Principles:
1. Strict Key Differentiation: Distinguishes institute, course code, branch, category,
   round, stage, list_type, and allocation level (level_key).
2. Exact Duplicate Collapse: Collapses exact duplicates while merging and preserving
   corroborating source references and page numbers.
3. Conflict Detection: Detects any differing ranks or percentiles on the same dimension key,
   writing an auditable conflict report to cutoffs/reports/reconciliation_conflicts_report.json.
4. Metric Independence: Closing rank (integer) and closing percentile (float) are treated as
   separate measurements and never conflated or merged.
5. Zero Fabrication: Records without valid values are never invented or assumed.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


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


def canonicalize_evidence_id(raw_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Normalize legacy 4-digit college codes and 9-digit course codes to canonical 5/10 digit format.

    Returns (canonical_id, source_evidence_id_if_modified).
    """
    if not raw_id:
        return None, None
    raw_s = str(raw_id).strip()
    norm = raw_s
    # 1. Normalize EV-1002-... -> EV-01002-...
    norm = re.sub(r"^EV-(\d{4})-", r"EV-0\1-", norm)
    # 2. Normalize colon format institute code: 2020-21:1002:... -> 2020-21:01002:...
    norm = re.sub(r"^(\d{4}-\d{2}):(\d{4}):", r"\1:0\2:", norm)
    # 3. Normalize 9-digit course code in colon format: ...:100224210:... -> ...:0100224210:...
    norm = re.sub(r"^(\d{4}-\d{2}:\d{5}):(\d{9}):", r"\1:0\2:", norm)
    norm = re.sub(r"^(\d{4}-\d{2}):(\d{4}):(\d{9}):", r"\1:0\2:0\3:", norm)
    source_id = raw_s if norm != raw_s else None
    return norm, source_id


class CutoffReconciler:
    """Merges and reconciles multi-year cutoff records across staging directories."""

    def __init__(
        self,
        out_dir: Union[str, Path] = "cutoffs/phase3_final_staging",
        reports_dir: Union[str, Path] = "cutoffs/reports",
        dry_run: bool = False,
    ):
        self.out_dir = Path(out_dir)
        self.reports_dir = Path(reports_dir)
        self.dry_run = dry_run

        # Audit registries
        self.conflicts: List[Dict[str, Any]] = []
        self.exact_duplicates_collapsed = 0
        self.total_cutoffs_merged = 0
        self.records_by_year: Dict[str, int] = defaultdict(int)
        self.files_by_year: Dict[str, int] = defaultdict(int)

    def reconcile_college_records(
        self,
        base_record: Optional[Dict[str, Any]],
        new_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge cutoffs from new_record into base_record, detecting duplicates and conflicts."""
        if base_record is None:
            # Deep clone new_record as starting base
            base_record = json.loads(json.dumps(new_record))
        else:
            # Check metadata consistency
            ay = base_record.get("academic_year")
            code = base_record.get("institute_code")

            # Index branches in base_record by (course_code, branch_name_lower)
            branch_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for b in base_record.get("branches", []):
                c_code = str(b.get("course_code") or "").strip()
                b_name = str(b.get("branch") or "").strip().lower()
                branch_map[(c_code, b_name)] = b

            for new_b in new_record.get("branches", []):
                new_c_code = str(new_b.get("course_code") or "").strip()
                new_b_name = str(new_b.get("branch") or "").strip().lower()
                b_key = (new_c_code, new_b_name)

                if b_key not in branch_map:
                    # Add complete new branch to base
                    base_record["branches"].append(json.loads(json.dumps(new_b)))
                    branch_map[b_key] = base_record["branches"][-1]
                    continue

                target_b = branch_map[b_key]
                # Index categories in target_b by category token
                cat_map: Dict[str, Dict[str, Any]] = {}
                for c in target_b.get("categories", []):
                    tok = str(c.get("category") or "").strip().upper()
                    cat_map[tok] = c

                for new_cat in new_b.get("categories", []):
                    new_tok = str(new_cat.get("category") or "").strip().upper()
                    if new_tok not in cat_map:
                        target_b["categories"].append(json.loads(json.dumps(new_cat)))
                        cat_map[new_tok] = target_b["categories"][-1]
                        continue

                    target_cat = cat_map[new_tok]
                    # Index existing cutoffs by 4-tuple key: (round, stage, list_type, level_key)
                    cutoff_map: Dict[Tuple[int, str, str, str], Dict[str, Any]] = {}
                    for cut in target_cat.get("cutoffs", []):
                        c_key = (
                            int(cut.get("round", 1)),
                            str(cut.get("stage", "1")).strip().upper(),
                            canonical_list_type(cut.get("list_type", "CAP")).upper(),
                            str(cut.get("level_key", "")).strip().upper(),
                        )
                        cutoff_map[c_key] = cut

                    for new_cut in new_cat.get("cutoffs", []):
                        c_key = (
                            int(new_cut.get("round", 1)),
                            str(new_cut.get("stage", "1")).strip().upper(),
                            canonical_list_type(new_cut.get("list_type", "CAP")).upper(),
                            str(new_cut.get("level_key", "")).strip().upper(),
                        )

                        if c_key in cutoff_map:
                            existing_cut = cutoff_map[c_key]
                            e_rank = existing_cut.get("closing_rank")
                            e_perc = existing_cut.get("closing_percentile")
                            n_rank = new_cut.get("closing_rank")
                            n_perc = new_cut.get("closing_percentile")

                            # Check if identical (exact duplicate)
                            if e_rank == n_rank and (e_perc is None or n_perc is None or round(e_perc, 5) == round(n_perc, 5)):
                                self.exact_duplicates_collapsed += 1
                                # Preserve corroborating source reference if different
                                e_src = existing_cut.get("source_file")
                                n_src = new_cut.get("source_file")
                                if n_src and n_src != e_src:
                                    corrob = existing_cut.setdefault("corroborating_sources", [])
                                    if n_src not in corrob:
                                        corrob.append(n_src)
                                # Preserve provenance fields
                                for prov_field in ("source_evidence_id", "source_list_type"):
                                    if prov_field in new_cut and prov_field not in existing_cut:
                                        existing_cut[prov_field] = new_cut[prov_field]
                            else:
                                # Conflict detected
                                conflict_entry = {
                                    "academic_year": ay,
                                    "institute_code": code,
                                    "branch": new_b.get("branch"),
                                    "category": new_tok,
                                    "round": c_key[0],
                                    "stage": c_key[1],
                                    "list_type": c_key[2],
                                    "level_key": c_key[3],
                                    "existing_cutoff": {"rank": e_rank, "percentile": e_perc, "source": existing_cut.get("source_file")},
                                    "incoming_cutoff": {"rank": n_rank, "percentile": n_perc, "source": new_cut.get("source_file")},
                                }
                                self.conflicts.append(conflict_entry)
                        else:
                            target_cat["cutoffs"].append(json.loads(json.dumps(new_cut)))
                            cutoff_map[c_key] = target_cat["cutoffs"][-1]

        # Post-merge normalization pass: ensure canonical institute code, course code, and evidence IDs
        if base_record:
            if base_record.get("institute_code"):
                raw_code = str(base_record["institute_code"]).strip()
                if len(raw_code) == 4 and raw_code.isdigit():
                    base_record["institute_code"] = raw_code.zfill(5)
            for b in base_record.get("branches", []):
                c_code = str(b.get("course_code") or "").strip()
                if len(c_code) == 9 and c_code.isdigit():
                    b["course_code"] = c_code.zfill(10)
                for cat in b.get("categories", []):
                    for cut in cat.get("cutoffs", []):
                        raw_ev = cut.get("evidence_id")
                        if raw_ev:
                            norm_ev, src_ev = canonicalize_evidence_id(raw_ev)
                            if norm_ev:
                                cut["evidence_id"] = norm_ev
                            if src_ev and not cut.get("source_evidence_id"):
                                cut["source_evidence_id"] = src_ev

        return base_record

    def reconcile_sources(
        self,
        source_dirs: List[Path],
    ) -> Dict[str, Any]:
        """Load and merge all cutoff files from supplied source directories."""
        # Index files by (academic_year, institute_code)
        grouped_files: Dict[Tuple[str, str], List[Path]] = defaultdict(list)

        for s_dir in source_dirs:
            if not s_dir.is_dir():
                print(f"Warning: Source directory not found: {s_dir}", file=sys.stderr)
                continue

            for year_dir in sorted(s_dir.iterdir()):
                if not year_dir.is_dir() or not re.match(r"^\d{4}-\d{2}$", year_dir.name):
                    continue
                ay = year_dir.name
                for fpath in sorted(year_dir.glob("*.json")):
                    if fpath.name.startswith((".", "_")) or fpath.name in ("manifest.json", "schema.json"):
                        continue
                    code_match = re.match(r"^(\d{4,5})", fpath.stem)
                    if not code_match:
                        continue
                    code = code_match.group(1).zfill(5)
                    grouped_files[(ay, code)].append(fpath)

        # Merge each (academic_year, institute_code)
        final_colleges: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for (ay, code), files in sorted(grouped_files.items()):
            merged: Optional[Dict[str, Any]] = None
            for fp in files:
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                    merged = self.reconcile_college_records(merged, data)
                except Exception as exc:
                    print(f"Error reading {fp}: {exc}", file=sys.stderr)

            if merged:
                final_colleges[(ay, code)] = merged
                # Count cutoffs
                c_cnt = sum(
                    len(cat.get("cutoffs", []))
                    for b in merged.get("branches", [])
                    for cat in b.get("categories", [])
                )
                self.records_by_year[ay] += c_cnt
                self.files_by_year[ay] += 1
                self.total_cutoffs_merged += c_cnt

        # Write to final staging if not dry_run
        if not self.dry_run:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            for (ay, code), data in sorted(final_colleges.items()):
                ydir = self.out_dir / ay
                ydir.mkdir(parents=True, exist_ok=True)
                out_file = ydir / f"{code}.json"
                out_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        summary_report = {
            "reconciliation_timestamp": datetime.now(timezone.utc).isoformat(),
            "target_staging_directory": str(self.out_dir),
            "total_cutoffs_merged": self.total_cutoffs_merged,
            "exact_duplicates_collapsed": self.exact_duplicates_collapsed,
            "conflicts_detected": len(self.conflicts),
            "years_reconciled": sorted(list(self.records_by_year.keys())),
            "counts_by_year": dict(self.records_by_year),
            "files_by_year": dict(self.files_by_year),
            "dry_run": self.dry_run,
        }

        # Write reports
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        (self.reports_dir / "reconciliation_summary_report.json").write_text(
            json.dumps(summary_report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (self.reports_dir / "year_by_year_merge_report.json").write_text(
            json.dumps({
                "counts_by_year": dict(self.records_by_year),
                "files_by_year": dict(self.files_by_year),
            }, indent=2), encoding="utf-8"
        )
        (self.reports_dir / "reconciliation_conflicts_report.json").write_text(
            json.dumps({
                "total_conflicts": len(self.conflicts),
                "conflicts": self.conflicts,
            }, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return summary_report


def main():
    ap = argparse.ArgumentParser(
        description="Reconcile historical and current cutoff records into phase3_final_staging (AI-con Phase 3)"
    )
    ap.add_argument(
        "--historical-dir",
        default="cutoffs/historical_adapted_staging",
        help="Path to adapted historical cutoff directory (e.g. 2020-21 through 2022-23)",
    )
    ap.add_argument(
        "--current-dir",
        default="cutoffs/adapted_staging",
        help="Path to adapted current-year cutoff directory (e.g. 2023-24 through 2025-26)",
    )
    ap.add_argument(
        "--out", "-o",
        dest="out_dir",
        default="cutoffs/phase3_final_staging",
        help="Target chronological merged staging directory",
    )
    ap.add_argument(
        "--reports-dir", "-r",
        default="cutoffs/reports",
        help="Path to directory for audit reports",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Audit merge without writing files to final staging",
    )
    args = ap.parse_args()

    hist_p = Path(args.historical_dir)
    curr_p = Path(args.current_dir)
    out_p = Path(args.out_dir)
    rep_p = Path(args.reports_dir)

    print("=" * 70)
    print("AI-CON PHASE 3: MULTI-YEAR CUTOFF DATA RECONCILIATION")
    print(f"Historical Source: {hist_p}")
    print(f"Current Source:    {curr_p}")
    print(f"Target Staging:    {out_p}")
    print("=" * 70)

    reconciler = CutoffReconciler(out_dir=out_p, reports_dir=rep_p, dry_run=args.dry_run)
    sources = [p for p in (hist_p, curr_p) if p.is_dir()]
    if not sources:
        print(f"Error: Neither {hist_p} nor {curr_p} exists.", file=sys.stderr)
        sys.exit(1)

    report = reconciler.reconcile_sources(sources)

    print(f"\nTotal Cutoffs Reconciled:       {report['total_cutoffs_merged']:,}")
    print(f"Exact Duplicates Collapsed:     {report['exact_duplicates_collapsed']:,}")
    print(f"Conflicts Requiring Review:     {report['conflicts_detected']:,}")
    print("\nCutoff Breakdown by Academic Year:")
    for yr, cnt in sorted(report["counts_by_year"].items()):
        files_cnt = report["files_by_year"].get(yr, 0)
        print(f"  - {yr}: {cnt:,} cutoffs across {files_cnt} college records")

    print(f"\nAudit reports saved to: {rep_p}/")
    print("=" * 70)
    print("RECONCILIATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
