"""
Historical Cutoff PDF Extractor (AI-con Phase 3)
------------------------------------------------
Extracts official MHT-CET CAP cutoff figures from historical PDFs (2020-21, 2021-22, 2022-23)
into the raw candidate JSON format under cutoffs/historical_raw_staging/.

Reuses the proven extraction architecture from extract_data_v4.py:
- Parses FORMAT B (Maharashtra State and Minority quota seat cutoff tables with stage rows).
- Parses FORMAT A (All India Merit seat cutoff lists).
- Extracts institute code, course code, branch, quota category token, closing rank, closing percentile.
- Maintains strict source file and page-number provenance on every entry.
- Emits detailed extraction audit report under cutoffs/reports/historical_extraction_report.json.

Requirements:
- pdfplumber (pip install pdfplumber)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Constants & Patterns
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "1": 1, "2": 2, "3": 3, "4": 4}

RE_YEAR_RANGE = re.compile(r"(20\d{2})\s*[-\u2013/]\s*(\d{2,4})")
RE_YEAR_SIMPLE = re.compile(r"\b(202[0-9])\b")
RE_ROUND = re.compile(r"(?:CAP\s*)?Round\s*[-\u2013:]?\s*(IV|III|II|I|[1-4])\b", re.I)

RE_COLLEGE = re.compile(r"^(\d{3,6})\s*-\s*(.+)$")
RE_COURSE = re.compile(r"^(\d{8,10})\s*-\s*(.+)$")
RE_STATUS = re.compile(r"^Status:\s*(.*)$", re.I)
RE_CATEGORY_TOKEN = re.compile(r"^[A-Z0-9]{3,14}$")
RE_RANK_ROW = re.compile(r"^(I{1,3}|IV|[1-4])\s+(.*)$")
RE_PCT_ROW = re.compile(r"^(\([\d.]+\)\s*)+$")
RE_INT = re.compile(r"^\d{1,7}$")
RE_HOME_UNIVERSITY = re.compile(r"Home\s*University\s*:\s*(.+)$", re.I)

SECTION_HEADS = [
    "Home University Seats Allotted to Home University Candidates",
    "Home University Seats Allotted to Other Than Home University Candidates",
    "Other Than Home University Seats Allotted to Other Than Home University Candidates",
    "Other Than Home University Seats Allotted to Home University Candidates",
    "State Level",
]

COURSE_START_WORDS = set("""Computer Information Electronics Electrical Mechanical Civil Chemical Artificial
Data Robotics Instrumentation Industrial Automation Textile Production Aeronautical Biomedical Bio
Metallurgy Manufacturing Polymer Fibres Dyestuff Food Pharmaceuticals Pharmaceutical Oil Paper Petro
Surface Cyber Mechatronics Mining Internet Structural Environmental VLSI""".split())


def slug(s: Optional[str]) -> str:
    """Generate safe URL/filename slug."""
    return re.sub(r"[^a-z0-9]+", "_", (s or "college").lower()).strip("_")[:60] or "college"


def detect_year_from_pdf(path: Path, first_page_text: str) -> str:
    """Detect academic year using text search first, then filename heuristics."""
    # 1. Search text for standard range: e.g. 2020-21 or 2020-2021
    m = RE_YEAR_RANGE.search(first_page_text or "")
    if m:
        y = int(m.group(1))
        return f"{y}-{(y + 1) % 100:02d}"

    # 2. Search filename for range
    m_fn = RE_YEAR_RANGE.search(path.name)
    if m_fn:
        y = int(m_fn.group(1))
        return f"{y}-{(y + 1) % 100:02d}"

    # 3. Fallback to 4-digit year in filename (e.g. 2020ENGG -> 2020-21)
    m_simp = RE_YEAR_SIMPLE.search(path.name)
    if m_simp:
        y = int(m_simp.group(1))
        return f"{y}-{(y + 1) % 100:02d}"

    return "unknown"


def detect_round_from_pdf(path: Path, first_page_text: str) -> Optional[int]:
    """Detect CAP round from page header or filename."""
    # 1. Page text header check
    m = RE_ROUND.search(first_page_text or "")
    if m:
        tok = m.group(1).upper()
        if tok in ROMAN:
            return ROMAN[tok]

    # 2. Filename check
    m_fn = RE_ROUND.search(path.name)
    if m_fn:
        tok = m_fn.group(1).upper()
        if tok in ROMAN:
            return ROMAN[tok]

    # 3. Check for patterns like CAP1, CAP2, CAP3
    m_cap = re.search(r"CAP([1-3])", path.name, re.I)
    if m_cap:
        return int(m_cap.group(1))

    return None


def detect_format(text: str) -> Optional[str]:
    """Classify PDF layout format."""
    head = (text or "")[:500]
    if "Seat Matrix" in head or "Provisional Seat Matrix" in head:
        return None
    if "All India Seats" in head:
        return "all_india"
    if "Maharashtra & Minority Seats" in head or "Cut Off List" in head:
        return "state_level"
    return "state_level"  # Default for MHT-CET CAP cutoff lists


def evidence_id(r: Dict[str, Any]) -> str:
    code = str(r['institute_code']).strip().zfill(5)
    c_code = str(r.get('course_code') or '').strip()
    if c_code and len(c_code) == 9 and c_code.isdigit():
        c_code = c_code.zfill(10)
    rnd = r.get("cap_round") if r.get("cap_round") is not None else "NA"
    return (
        f"{r['academic_year']}:{code}:{c_code or 'na'}:"
        f"{r.get('level_key', 'na')}:{r['seat_type']}:R{rnd}:S{r.get('stage', 1)}"
    )


def parse_state_level(
    text: str,
    year: str,
    cap_round: int,
    source_file: str,
    page_no: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parse FORMAT B category-column / stage-row cutoff pages."""
    records: List[Dict[str, Any]] = []
    quarantined: List[Dict[str, Any]] = []
    lines = [line for line in (text or "").split("\n")]
    ctx: Dict[str, Any] = {
        "college_code": None,
        "college_name": None,
        "course_code": None,
        "course_name": None,
        "status": None,
        "section": None,
        "home_university": None,
    }
    header: Optional[List[str]] = None
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        line = raw.strip()
        i += 1
        if not line:
            continue

        m_course = RE_COURSE.match(line)
        if m_course:
            ctx.update(
                course_code=m_course.group(1),
                course_name=m_course.group(2).strip(),
                status=None,
                section=None,
            )
            header = None
            continue

        m_stat = RE_STATUS.match(line)
        if m_stat:
            status_text = m_stat.group(1).strip()
            hu = RE_HOME_UNIVERSITY.search(status_text)
            if hu:
                ctx["home_university"] = hu.group(1).strip()
                status_text = RE_HOME_UNIVERSITY.sub("", status_text).strip()
            ctx["status"] = status_text
            continue

        if line in SECTION_HEADS:
            ctx["section"] = line
            header = None
            continue

        m_coll = RE_COLLEGE.match(line)
        if m_coll and not RE_COURSE.match(line):
            ctx.update(
                college_code=m_coll.group(1),
                college_name=m_coll.group(2).strip(),
                course_code=None,
                course_name=None,
                status=None,
                section=None,
                home_university=None,
            )
            header = None
            continue

        if line.startswith("Stage"):
            toks = line.split()[1:]
            # Handle PDF-wrap quirk where trailing suffix lands on next line
            if toks and i < n:
                nxt = lines[i].strip()
                if nxt and RE_CATEGORY_TOKEN.match(nxt) and len(nxt) <= 3 and not RE_RANK_ROW.match(nxt):
                    toks[-1] = toks[-1] + nxt
                    i += 1
            header = toks
            continue

        m_rank = RE_RANK_ROW.match(line)
        if m_rank and header:
            stage_tok = m_rank.group(1).upper()
            stage = ROMAN.get(stage_tok, 1)
            vals = m_rank.group(2).split()
            if len(vals) != len(header):
                quarantined.append({
                    "problem": "rank_count_mismatch",
                    "stage": stage,
                    "header": header,
                    "values": vals,
                    "college_code": ctx["college_code"],
                    "course_code": ctx["course_code"],
                    "source_file": source_file,
                    "page": page_no,
                })
                continue

            if i < n and RE_PCT_ROW.match(lines[i].strip()):
                pct_line = lines[i].strip()
                i += 1
                pcts = re.findall(r"\(([\d.]+)\)", pct_line)
            else:
                pcts = [None] * len(vals)

            if len(pcts) != len(vals):
                pcts = (pcts + [None] * len(vals))[:len(vals)]

            for cat, rank_s, pct_s in zip(header, vals, pcts):
                rec = {
                    "academic_year": year,
                    "cap_round": cap_round,
                    "stage": stage,
                    "list_type": "CAP",
                    "institute_code": ctx["college_code"],
                    "institute_name": ctx["college_name"],
                    "course_code": ctx["course_code"],
                    "course_name": ctx["course_name"],
                    "status": ctx["status"],
                    "home_university": ctx.get("home_university"),
                    "level_label": ctx["section"] or "State Level",
                    "level_key": slug(ctx["section"] or "state_level"),
                    "seat_type": cat,
                    "closing_rank": int(rank_s) if RE_INT.match(rank_s) else None,
                    "closing_percentile": float(pct_s) if pct_s else None,
                    "source_file": source_file,
                    "page": page_no,
                }
                problems = []
                if not rec["institute_code"]:
                    problems.append("no_institute")
                if not rec["course_code"]:
                    problems.append("no_course")
                if rec["closing_rank"] is None or rec["closing_rank"] <= 0:
                    problems.append("bad_rank")
                if rec["closing_percentile"] is not None and not (0 <= rec["closing_percentile"] <= 100):
                    problems.append("percentile_out_of_range")

                if problems:
                    rec["problems"] = problems
                    quarantined.append(rec)
                else:
                    records.append(rec)
            continue

    return records, quarantined


def build_raw_college_files(all_records: List[Dict[str, Any]], out_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Assemble records into college JSON files under <out_dir>/<academic_year>/."""
    years: Dict[str, Dict[str, Any]] = defaultdict(dict)
    now = datetime.now(timezone.utc).isoformat()

    for r in all_records:
        year = r["academic_year"]
        institute_code = str(r["institute_code"]).strip()
        # Zero-pad 4-digit codes to 5 digits
        if len(institute_code) == 4 and institute_code.isdigit():
            institute_code = institute_code.zfill(5)

        college = years[year].setdefault(
            institute_code,
            {
                "academic_year": year,
                "institute_code": institute_code,
                "institute_name": r.get("institute_name"),
                "status": r.get("status"),
                "home_university": r.get("home_university"),
                "source_files": set(),
                "branches": {},
                "extracted_at": now,
            },
        )

        if not college["institute_name"] and r.get("institute_name"):
            college["institute_name"] = r["institute_name"]
        if not college["status"] and r.get("status"):
            college["status"] = r["status"]
        if not college["home_university"] and r.get("home_university"):
            college["home_university"] = r["home_university"]

        college["source_files"].add(r["source_file"])

        course_code = r["course_code"]
        branch = college["branches"].setdefault(
            course_code,
            {
                "course_code": course_code,
                "branch": r.get("course_name"),
                "categories": {},
            },
        )

        cat_name = r.get("seat_type") or "UNKNOWN"
        category = branch["categories"].setdefault(cat_name, {"category": cat_name, "cutoffs": []})

        round_no = r.get("cap_round", 1)
        stage = r.get("stage", 1)
        level_key = r.get("level_key", "na")

        duplicate = any(
            c.get("round") == round_no and c.get("stage") == stage and c.get("level_key") == level_key
            for c in category["cutoffs"]
        )
        if duplicate:
            continue

        entry: Dict[str, Any] = {
            "round": round_no,
            "stage": stage,
            "level_key": level_key,
            "level_label": r.get("level_label"),
            "list_type": r.get("list_type", "CAP"),
            "closing_rank": r.get("closing_rank"),
            "closing_percentile": r.get("closing_percentile"),
            "evidence_id": evidence_id(r),
            "source_file": r.get("source_file"),
            "page": r.get("page"),
        }
        category["cutoffs"].append(entry)

    # Write out JSON files
    for year, colleges in years.items():
        ydir = out_dir / year
        ydir.mkdir(parents=True, exist_ok=True)

        for code, college in sorted(colleges.items()):
            college["source_files"] = sorted(list(college["source_files"]))
            branches_list = []
            for b_code, b_obj in sorted(college["branches"].items()):
                categories_list = []
                for cat_token, cat_obj in sorted(b_obj["categories"].items()):
                    cat_obj["cutoffs"].sort(key=lambda x: (x.get("round", 999), x.get("stage", 999)))
                    categories_list.append(cat_obj)
                b_obj["categories"] = categories_list
                branches_list.append(b_obj)
            college["branches"] = branches_list

            filename = f"{code}_{slug(college['institute_name'])}.json"
            (ydir / filename).write_text(json.dumps(college, indent=2, ensure_ascii=False), encoding="utf-8")

    return years


def extract_pdfs(
    input_dir: Path,
    out_dir: Path,
    report_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute complete extraction pipeline over historical PDF folder."""
    try:
        import pdfplumber
    except ImportError:
        print(
            "ERROR: 'pdfplumber' is required for historical PDF table extraction.\n"
            "Please install it using: pip install pdfplumber",
            file=sys.stderr,
        )
        sys.exit(1)

    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    all_records: List[Dict[str, Any]] = []
    all_quarantined: List[Dict[str, Any]] = []
    file_reports: List[Dict[str, Any]] = []

    print(f"Found {len(pdfs)} historical PDFs to extract.")

    for idx, p in enumerate(pdfs, 1):
        print(f"[{idx}/{len(pdfs)}] Inspecting: {p.name} ({p.stat().st_size:,} bytes)...")
        with pdfplumber.open(p) as pdf:
            first_text = pdf.pages[0].extract_text() if pdf.pages else ""
            year = detect_year_from_pdf(p, first_text)
            cap_round = detect_round_from_pdf(p, first_text) or 1
            fmt = detect_format(first_text)

            rec_count = 0
            quar_count = 0

            for pno, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if not text:
                    continue
                recs, quar = parse_state_level(text, year, cap_round, p.name, pno)
                all_records.extend(recs)
                all_quarantined.extend(quar)
                rec_count += len(recs)
                quar_count += len(quar)

            file_reports.append({
                "filename": p.name,
                "academic_year": year,
                "cap_round": cap_round,
                "format": fmt,
                "pages": len(pdf.pages),
                "extracted_records": rec_count,
                "quarantined_records": quar_count,
            })
            print(f"    -> Year: {year}, Round: {cap_round}, Extracted: {rec_count:,} records.")

    out_dir.mkdir(parents=True, exist_ok=True)
    years_dict = build_raw_college_files(all_records, out_dir)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_pdfs": len(pdfs),
        "total_extracted_records": len(all_records),
        "total_quarantined_records": len(all_quarantined),
        "years_covered": {y: len(c) for y, c in years_dict.items()},
        "file_details": file_reports,
    }

    if report_dir:
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / "historical_extraction_report.json"
        report_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nExtraction audit report saved to: {report_file}")

    return summary


def main():
    ap = argparse.ArgumentParser(description="Extract historical MHT-CET CAP cutoff PDFs (AI-con Phase 3)")
    ap.add_argument(
        "--input", "-i",
        default="cutoffs/historical_pdf_input",
        help="Path to folder containing historical cutoff PDFs",
    )
    ap.add_argument(
        "--out", "-o",
        default="cutoffs/historical_raw_staging",
        help="Path to staging destination for raw extracted JSON records",
    )
    ap.add_argument(
        "--reports-dir", "-r",
        default="cutoffs/reports",
        help="Directory to save extraction audit report",
    )
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.out)
    rep_path = Path(args.reports_dir)

    print("=" * 70)
    print("AI-CON PHASE 3: HISTORICAL CUTOFF PDF EXTRACTION")
    print(f"Input:   {in_path}")
    print(f"Output:  {out_path}")
    print("=" * 70)

    extract_pdfs(in_path, out_path, rep_path)
    print("=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
