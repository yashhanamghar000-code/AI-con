#!/usr/bin/env python3
"""
MHT-CET CAP cutoff PDF -> per-year, per-college JSON + training data.

Handles the two real CET Cell cutoff PDF layouts:
  FORMAT B "state_level" - "Cut Off List for Maharashtra & Minority Seats of CAP
     Round X ..." - category columns (GOPENS, GSCH, LOBCO, ...) under section
     headings (State Level / Home University Seats Allotted to.../ Other Than
     Home University Seats Allotted to...), rank row + percentile row per stage.
  FORMAT A "all_india" - "Cut Off List for All India Seats of CAP Round X ..."
     - a flat per-choice-code table: Sr.No, All India Merit rank(percentile),
       Choice Code, Institute Name, Course Name, Exam, Type, Seat Type.

Deliberately NOT parsed: seat-vacancy / seat-matrix PDFs (e.g. PHSeatvacancy.pdf,
"Provisional Seat Matrix for CAP Round..."). Those are intake/reservation
tables, not cutoffs, and are out of scope here as agreed.

Install:   pip install pdfplumber
Run:       python extract_cutoffs.py --input ./cutoff_pdfs --out ./out

Input layout: put PDFs under a folder named for the academic year, e.g.
    cutoff_pdfs/2023-24/2023ENGG_CAP1_CutOff.pdf
    cutoff_pdfs/2023-24/2023ENGG_CAP1_AI_CutOff.pdf
Year is read from the folder name, falling back to filename/PDF title text.
CAP round is read from the PDF's own title line ("CAP Round - I" / "CAP Round I").

Output:
  out/<year>/<institute_code>_<slug>.json   one file per college per year,
       merging BOTH state-level and all-India records for that college
  out/<year>/_index.json
  out/training/records_<year>.jsonl + all_records.csv   flat rows for the
       cutoff predictor (one row per category/seat-type/round/stage cutoff)
  out/training/sft_grounded_qa.jsonl   evidence-grounded Q&A + abstention
       examples for the SLM (behaviour only - no raw numbers memorised)
  out/quarantine.jsonl   rows that could not be safely placed
  out/extraction_report.json   per-file stats, warnings, low-confidence splits

IMPORTANT CAVEAT (read before trusting institute/course names from the
all_india format): that format's text does not reliably mark where an
institute's name ends and the course name begins once either wraps across a
line (both are free text, e.g. "Pune Institute of Computer Technology" vs
course "Computer Engineering" - "Computer" starts both). This script
resolves it with a self-learning cache: the institute_code (first 4-5 digits
of the choice code) is used to remember the institute's name the first time
it is seen cleanly (single-line, unambiguous), and every later row with the
same institute_code reuses that cached name. Rows whose institute name could
not be confirmed this way are kept (all numeric fields are always correct)
but flagged "name_confidence": "unverified" - don't train on those names
until you spot-check them or join against an official institute-code master
list (recommended either way; see extraction_report.json -> low_confidence_names).
"""
import argparse, csv, json, random, re, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

PARSER_VERSION = "0.3-flattened-output-v1"
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}

RE_YEAR_RANGE = re.compile(r"(20\d{2})\s*[-\u2013/]\s*(\d{2,4})")
RE_ROUND = re.compile(r"CAP\s*Round\s*[-\u2013:]?\s*(IV|III|II|I)\b", re.I)
RE_COLLEGE = re.compile(r"^(\d{3,6})\s*-\s*(.+)$")
RE_COURSE = re.compile(r"^(\d{8,10})\s*-\s*(.+)$")
RE_STATUS = re.compile(r"^Status:\s*(.*)$", re.I)
RE_CATEGORY_TOKEN = re.compile(r"^[A-Z0-9]{3,14}$")
RE_RANK_ROW = re.compile(r"^(I{1,3}|IV)\s+(.*)$")
RE_PCT_ROW = re.compile(r"^(\([\d.]+\)\s*)+$")
RE_INT = re.compile(r"^\d{1,7}$")

SECTION_HEADS = [
    "Home University Seats Allotted to Home University Candidates",
    "Home University Seats Allotted to Other Than Home University Candidates",
    "Other Than Home University Seats Allotted to Other Than Home University Candidates",
    "Other Than Home University Seats Allotted to Home University Candidates",
    "State Level",
]

FAMILIES = [
    ("computing", ["computer", "information technology", "artificial intelligence", "data science",
                   "cyber", "software", "machine learning", "iot", "internet of things"]),
    ("electronics_telecom", ["electronics", "telecommunication", "instrumentation", "vlsi"]),
    ("electrical", ["electrical", "power"]),
    ("mechanical", ["mechanical", "mechatronics", "automobile", "production", "industrial", "robotics"]),
    ("civil", ["civil", "structural", "construction", "environmental"]),
    ("chemical_bio", ["chemical", "bio", "petro", "polymer", "oil", "paint", "food", "textile", "pharma"]),
]

COURSE_START_WORDS = set("""Computer Information Electronics Electrical Mechanical Civil Chemical Artificial
Data Robotics Instrumentation Industrial Automation Textile Production Aeronautical Biomedical Bio
Metallurgy Manufacturing Polymer Fibres Dyestuff Food Pharmaceuticals Pharmaceutical Oil Paper Petro
Surface Cyber Mechatronics Mining Internet Structural Environmental VLSI""".split())

# Best-effort seat-type decoder, built from the legend every CET cutoff PDF
# itself prints: "Starting character G-General, L-Ladies, End character
# H-Home University, O-Other than Home University, S-State Level, AI- All
# India Seat." This is NOT an official CET rule table - it is read off the
# code's own prefix/body/suffix letters, so treat category_meaning as a
# readable gloss for a human or an SLM, not as ground truth for eligibility.
# Always verify against the active brochure before using it for anything
# that affects a real decision (see 02_MHT_CET_Admission_Data_and_Rules.md).
STANDALONE_CATEGORY_LABELS = {
    "TFWS": "Tuition Fee Waiver Scheme (state level)",
    "EWS": "Economically Weaker Section (state level)",
    "ORPHAN": "Orphan category (state level)",
    "AI": "All India seat",
}
PREFIX_LABELS = [("PWDROBC", "Persons with Disability, reserved-category"),
                 ("DEFROBC", "Defense quota, reserved-category"),
                 ("PWDR", "Persons with Disability, reserved-category"),
                 ("DEFR", "Defense quota, reserved-category"),
                 ("PWD", "Persons with Disability"),
                 ("DEF", "Defense quota"),
                 ("G", "General (male)"),
                 ("L", "Ladies")]
BODY_LABELS = [("OPEN", "Open"), ("OBC", "Other Backward Class"), ("SBC", "Special Backward Class"),
               ("SC", "Scheduled Caste"), ("ST", "Scheduled Tribe"),
               ("NT1", "Nomadic Tribe 1"), ("NT2", "Nomadic Tribe 2"), ("NT3", "Nomadic Tribe 3"),
               ("VJ", "Vimukt Jati"), ("DT", "Denotified Tribe")]
SUFFIX_LABELS = {"H": "Home University seats", "O": "Other than Home University seats",
                 "S": "State Level"}


def decode_category(code):
    """Best-effort (prefix, body, suffix) gloss of a seat-type code. Returns
    (meaning_string, confidence) where confidence is 'best_effort' always -
    this is pattern-matched from the code's letters, not an official source."""
    if not code:
        return None, None
    if code in STANDALONE_CATEGORY_LABELS:
        return STANDALONE_CATEGORY_LABELS[code], "best_effort"
    rest = code
    prefix_label = None
    for p, label in PREFIX_LABELS:
        if rest.startswith(p):
            prefix_label, rest = label, rest[len(p):]
            break
    suffix_label = None
    if rest and rest[-1] in SUFFIX_LABELS:
        suffix_label, rest = SUFFIX_LABELS[rest[-1]], rest[:-1]
    body_label = None
    for b, label in BODY_LABELS:
        if rest == b:
            body_label = label
            break
    parts = [p for p in (prefix_label, body_label, suffix_label) if p]
    if len(parts) < 2:
        return None, None  # not enough matched to be worth guessing
    return ", ".join(parts), "best_effort"


RE_HOME_UNIVERSITY = re.compile(r"Home\s*University\s*:\s*(.+)$", re.I)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", (s or "college").lower()).strip("_")[:60] or "college"


def branch_family(name):
    n = (name or "").lower()
    for fam, keys in FAMILIES:
        if any(k in n for k in keys):
            return fam
    return "other"


def detect_year(path, text):
    for src in (str(path), text or ""):
        m = RE_YEAR_RANGE.search(src)
        if m:
            y = int(m.group(1))
            return f"{y}-{(y + 1) % 100:02d}"
    return "unknown"


def detect_round(text):
    m = RE_ROUND.search(text or "")
    return ROMAN.get(m.group(1).upper()) if m else None


def detect_format(text):
    head = (text or "")[:400]
    if "Seat Matrix" in head or "Provisional Seat Matrix" in head:
        return None  # explicitly excluded: intake/reservation table, not a cutoff list
    if "All India Seats" in head:
        return "all_india"
    if "Maharashtra & Minority Seats" in head:
        return "state_level"
    return None


def evidence_id(r):
    rnd = r.get("cap_round") if r.get("cap_round") is not None else "NA"
    return (f"{r['academic_year']}:{r['institute_code']}:{r['course_code']}:"
            f"{r.get('level_key','na')}:{r['seat_type']}:R{rnd}:S{r.get('stage',1)}")


# ---------------------------------------------------------------- FORMAT B --
def parse_state_level(text, year, cap_round, source_file, page_no):
    """Category-column / stage-row cutoff pages. Returns list of record dicts."""
    records, quarantined = [], []
    lines = [l for l in (text or "").split("\n")]
    ctx = {"college_code": None, "college_name": None, "course_code": None,
           "course_name": None, "status": None, "section": None, "home_university": None}
    header = None  # list of category tokens for current table
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        line = raw.strip()
        i += 1
        if not line:
            continue

        m = RE_COURSE.match(line)
        if m:
            ctx.update(course_code=m.group(1), course_name=m.group(2).strip(),
                       status=None, section=None)
            header = None
            continue
        m = RE_STATUS.match(line)
        if m:
            status_text = m.group(1).strip()
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
        m = RE_COLLEGE.match(line)
        if m and not RE_COURSE.match(line):
            ctx.update(college_code=m.group(1), college_name=m.group(2).strip(),
                       course_code=None, course_name=None, status=None, section=None,
                       home_university=None)
            header = None
            continue
        if line.startswith("Stage"):
            toks = line.split()[1:]
            # fix the PDF-wrap quirk where the last header token (e.g. PWDROBCS)
            # gets split and its tail ("S") lands alone on the very next line
            if toks and i < n:
                nxt = lines[i].strip()
                if nxt and RE_CATEGORY_TOKEN.match(nxt) and len(nxt) <= 3 and not RE_RANK_ROW.match(nxt):
                    toks[-1] = toks[-1] + nxt
                    i += 1
            header = toks
            continue

        m = RE_RANK_ROW.match(line)
        if m and header:
            stage = ROMAN.get(m.group(1))
            vals = m.group(2).split()
            if len(vals) != len(header):
                quarantined.append({
                    "problem": "rank_count_mismatch", "stage": stage,
                    "header": header, "values": vals,
                    "college_code": ctx["college_code"], "course_code": ctx["course_code"],
                    "source_file": source_file, "page": page_no,
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
                    "academic_year": year, "cap_round": cap_round, "stage": stage,
                    "list_type": "maharashtra_minority",
                    "institute_code": ctx["college_code"], "institute_name": ctx["college_name"],
                    "course_code": ctx["course_code"], "course_name": ctx["course_name"],
                    "status": ctx["status"], "home_university": ctx.get("home_university"),
                    "level_label": ctx["section"],
                    "level_key": slug(ctx["section"]),
                    "seat_type": cat,
                    "closing_rank": int(rank_s) if RE_INT.match(rank_s) else None,
                    "closing_percentile": float(pct_s) if pct_s else None,
                    "source_file": source_file, "page": page_no,
                }
                problems = []
                if not rec["institute_code"]:
                    problems.append("no_institute")
                if not rec["course_code"]:
                    problems.append("no_course")
                if rec["closing_rank"] is None:
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


# ---------------------------------------------------------------- FORMAT A --
ROW_TAIL_RE = re.compile(r"^(.*?)\s+(JEE\(Main\)|MHT-CET)\s+(\S+\s+to\s+\S+)\s+(\S+)\s*(.*)$", re.S)
ANCHOR_RE = re.compile(r"(\d+)\s+(\d+)\s+\(([\d.]+)\)\s+(\d{6,10})\s+")
FOOTER_RE = re.compile(r"\s*Cut Off Indicates.*$", re.S)


def split_inst_course(blob, inst_cache):
    """Return (institute_code, institute_name, course_name_part, confident).

    Course names in this dataset never contain a comma, while institute names
    almost always end in ", <City>". So when the text after the institute
    code has a comma, we only look for the institute/course boundary AFTER
    the last comma - this avoids false hits like "Institute of Computer
    Technology" (where "Computer" is part of the institute name, not the
    course) which a whole-string word search would misread. Only when there
    is no comma at all do we fall back to a whole-string search, and that
    fallback result is marked unverified since it has no comma to anchor it.
    """
    m = re.match(r"^(\d{3,6})\s*-\s*(.*)$", blob.strip())
    if not m:
        return None, blob, "", False
    code, rest = m.group(1), m.group(2)
    if code in inst_cache:
        cached = inst_cache[code]
        if rest.startswith(cached):
            return code, cached, rest[len(cached):].strip(), True

    last_comma = rest.rfind(",")
    if last_comma != -1:
        head, tail = rest[:last_comma + 1], rest[last_comma + 1:]
        tail_words = tail.split()
        split_i = next((idx for idx, w in enumerate(tail_words)
                        if w.strip(",") in COURSE_START_WORDS), None)
        if split_i is None:
            return code, rest, "", False
        inst = (head + " " + " ".join(tail_words[:split_i])).strip()
        course = " ".join(tail_words[split_i:])
        confident = code not in inst_cache
        return code, inst, course, confident

    words = rest.split()
    split_i = next((idx for idx, w in enumerate(words)
                    if w.strip(",") in COURSE_START_WORDS), None)
    if split_i is None:
        return code, rest, "", False
    inst = " ".join(words[:split_i])
    course = " ".join(words[split_i:])
    return code, inst, course, False  # no comma to anchor on - always unverified


def parse_all_india(text, year, cap_round, source_file, page_no, inst_cache):
    records, quarantined = [], []
    body = FOOTER_RE.sub("", text or "")
    parts = ANCHOR_RE.split(body)
    for i in range(1, len(parts) - 4, 5):
        srno, rank, pct, choice, blob = parts[i], parts[i + 1], parts[i + 2], parts[i + 3], parts[i + 4]
        blob = re.sub(r"\s+", " ", blob).strip()
        m = ROW_TAIL_RE.match(blob)
        if not m:
            quarantined.append({"problem": "row_tail_no_match", "choice_code": choice,
                                "blob": blob, "source_file": source_file, "page": page_no})
            continue
        inst_course1, exam, typ, seat, tail = m.groups()
        code, inst, course1, confident = split_inst_course(inst_course1, inst_cache)
        if code and confident and code not in inst_cache:
            inst_cache[code] = inst
        elif code in inst_cache:
            inst = inst_cache[code]
        course = (course1 + (" " + tail if tail else "")).strip()
        course = re.sub(r"\s+", " ", course)
        # defensive cleanup: a row that is the LAST one on a page can pick up
        # a stray "Sr.No," fragment from the next page's first row bleeding
        # into the page's extracted text (seen e.g. as "Civil Engineering 1,")
        # - course names in this dataset never legitimately end in a bare
        # 1-3 digit number followed by a comma, so this is always noise.
        course_before_cleanup = course
        course = re.sub(r"\s+\d{1,3},\s*$", "", course).strip()
        if course != course_before_cleanup:
            name_confidence_note = "trailing_fragment_stripped"
        else:
            name_confidence_note = None
        rec = {
            "academic_year": year, "cap_round": cap_round, "stage": 1,
            "list_type": "all_india",
            "institute_code": code, "institute_name": inst,
            "course_code": choice, "course_name": course,
            "status": None, "level_label": "All India", "level_key": "all_india",
            "seat_type": seat, "all_india_merit_no": int(rank),
            "closing_rank": int(rank), "closing_percentile": float(pct),
            "exam": exam, "candidature_type": typ,
            "name_confidence": "confident" if confident else "unverified",
            "course_name_note": name_confidence_note,
            "source_file": source_file, "page": page_no,
        }
        problems = []
        if not code:
            problems.append("no_institute")
        if not (0 <= rec["closing_percentile"] <= 100):
            problems.append("percentile_out_of_range")
        if problems:
            rec["problems"] = problems
            quarantined.append(rec)
        else:
            records.append(rec)
    return records, quarantined


# ---------------------------------------------------------------- DRIVER ----
def parse_pdf(path, inst_cache):
    records, quarantined, info = [], [], {"file": str(path), "pages": 0, "format": None}
    with pdfplumber.open(path) as pdf:
        first_text = pdf.pages[0].extract_text() or "" if pdf.pages else ""
        fmt = detect_format(first_text)
        year = detect_year(path, first_text)
        cap_round = detect_round(first_text)
        info.update(format=fmt, year=year, cap_round=cap_round)
        if fmt is None:
            info["warning"] = ("unrecognised_format (not an All-India or Maharashtra/Minority cutoff "
                                "list - skipped; seat-matrix/vacancy PDFs are expected to hit this)")
            return records, quarantined, info
        for pno, page in enumerate(pdf.pages, start=1):
            info["pages"] += 1
            text = page.extract_text()
            if not text:
                continue
            if fmt == "state_level":
                recs, quar = parse_state_level(text, year, cap_round, Path(path).name, pno)
            else:
                recs, quar = parse_all_india(text, year, cap_round, Path(path).name, pno, inst_cache)
            records += recs
            quarantined += quar
    info["records"] = len(records)
    info["quarantined"] = len(quarantined)
    return records, quarantined, info


def build_college_files(all_records, out):
    """
    Build the FLATTENED hierarchical JSON structure:

    out/
      <year>/
        <college_code>_<college_slug>.json

    Inside each college:
      college
        -> branches[]
          -> categories[]
            -> cutoffs[]   (one entry per round+stage; level_key/list_type
                            live ON each entry instead of as a nesting layer,
                            because a category's cutoff history commonly
                            spans more than one level across rounds - e.g.
                            GOPENH allotted "home-to-home" in round 1 but
                            "home-to-other" in round 2 - and an SLM reading
                            this should see that as ONE continuous history
                            for GOPENH, not two separate lists to merge.)

    Example:

    {
      "academic_year": "2025-26",
      "institute_code": "01002",
      "institute_name": "Government College of Engineering, Amravati",
      "status": "Government Autonomous",
      "home_university": "Shivaji University",
      "branches": [
        {
          "course_code": "0100224210",
          "branch": "Computer Science and Engineering",
          "branch_family": "computing",
          "categories": [
            {
              "category": "GOPENS",
              "category_meaning": "General (male), Open, State Level",
              "category_meaning_confidence": "best_effort",
              "cutoffs": [
                {
                  "round": 1, "stage": 1, "level_key": "state_level",
                  "closing_rank": 9196, "closing_percentile": 97.3737374,
                  "evidence_id": "...", "source_file": "...", "page": 2
                },
                {
                  "round": 2, "stage": 1, "level_key": "state_level",
                  "closing_rank": 8500, "closing_percentile": 98.1,
                  "evidence_id": "...", "source_file": "...", "page": 5
                }
              ]
            }
          ]
        }
      ]
    }

    Important:
    - All available CAP rounds are retained; nothing is hard-coded to 3/4 rounds.
    - State-level and All-India cutoffs for the same category sit in the same
      "cutoffs" list, distinguished by "list_type" on each entry, so a
      question like "show me every GOPENS cutoff this college had" doesn't
      require merging two different sub-lists.
    - Duplicate round/stage/level records are ignored.
    - Records are sorted branch -> category -> round -> stage.
    - category_meaning is a best-effort gloss read off the code's own
      letters (see decode_category docstring) - not an official CET source.
    """

    years = defaultdict(dict)
    now = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # 1. Create college -> branch -> category -> cutoffs structure
    # ------------------------------------------------------------------
    for r in all_records:
        year = r["academic_year"]
        institute_code = r["institute_code"]

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
                "parser_version": PARSER_VERSION,
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
                "branch_family": branch_family(r.get("course_name")),
                "branch_family_note": "discovery only; never use to substitute cutoffs",
                "categories": {},
            },
        )

        category_name = r.get("seat_type") or "UNKNOWN"
        category = branch["categories"].setdefault(category_name, {"category": category_name, "cutoffs": []})

        # One cutoff observation = one round + stage + level (a category can
        # legitimately be allotted under different levels across rounds).
        round_no = r.get("cap_round")
        stage = r.get("stage", 1)
        level_key = r.get("level_key", "na")

        duplicate = any(
            item.get("round") == round_no and item.get("stage") == stage and item.get("level_key") == level_key
            for item in category["cutoffs"]
        )
        if duplicate:
            continue

        entry = {
            "round": round_no,
            "stage": stage,
            "level_key": level_key,
            "level_label": r.get("level_label"),
            "list_type": r.get("list_type"),
            "closing_rank": r.get("closing_rank"),
            "closing_percentile": r.get("closing_percentile"),
            "evidence_id": evidence_id(r),
            "source_file": r.get("source_file"),
            "page": r.get("page"),
        }

        if r.get("list_type") == "all_india":
            entry["all_india_merit_no"] = r.get("all_india_merit_no")
            entry["exam"] = r.get("exam")
            entry["candidature_type"] = r.get("candidature_type")
            entry["name_confidence"] = r.get("name_confidence")
            if r.get("course_name_note"):
                entry["course_name_note"] = r.get("course_name_note")

        category["cutoffs"].append(entry)

    # ------------------------------------------------------------------
    # 2. Convert dictionaries to ordered JSON lists
    # ------------------------------------------------------------------
    for year, colleges in years.items():
        ydir = Path(out) / year
        ydir.mkdir(parents=True, exist_ok=True)

        index = []

        for institute_code, college in sorted(colleges.items()):
            college["source_files"] = sorted(college["source_files"])

            branches = []

            for branch_code, branch in sorted(
                college["branches"].items(),
                key=lambda item: ((item[1].get("branch") or "").lower(), item[0]),
            ):
                categories = []

                for category_name, category in sorted(branch["categories"].items(), key=lambda item: item[0]):
                    category["cutoffs"].sort(
                        key=lambda x: (
                            x.get("round") if x.get("round") is not None else 999,
                            x.get("stage") if x.get("stage") is not None else 999,
                        )
                    )
                    meaning, confidence = decode_category(category_name)
                    if meaning:
                        category["category_meaning"] = meaning
                        category["category_meaning_confidence"] = confidence
                    categories.append(category)

                branch["categories"] = categories
                branches.append(branch)

            college["branches"] = branches

            filename = f"{institute_code}_{slug(college['institute_name'])}.json"
            output_file = ydir / filename
            output_file.write_text(json.dumps(college, indent=2, ensure_ascii=False), encoding="utf-8")

            index.append({
                "institute_code": institute_code,
                "name": college["institute_name"],
                "file": filename,
                "branches": len(branches),
                "categories": sum(len(branch["categories"]) for branch in branches),
            })

        (ydir / "_index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    return years



def write_training(all_records, out, max_sft, seed=42):
    tdir = Path(out) / "training"
    tdir.mkdir(parents=True, exist_ok=True)
    by_year = defaultdict(list)
    flat = []
    for r in all_records:
        r = dict(r, evidence_id=evidence_id(r), branch_family=branch_family(r["course_name"]))
        by_year[r["academic_year"]].append(r)
        flat.append(r)
    for y, rows in by_year.items():
        with open(tdir / f"records_{y}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if flat:
        cols = sorted({k for r in flat for k in r.keys()})
        with open(tdir / "all_records.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(flat)

    system = ("You are an admission decision-support assistant. Use only the supplied evidence. "
              "Cite evidence IDs in [brackets]. Never promise admission. If evidence is missing, "
              "answer status=insufficient_evidence and say what is missing.")
    groups = defaultdict(list)
    for r in flat:
        if r.get("name_confidence") == "unverified":
            continue  # don't train the SLM on unverified names
        groups[(r["academic_year"], r["institute_code"], r["course_code"],
                r.get("level_key", "na"), r["seat_type"])].append(r)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    examples = []
    for k in keys[:max_sft]:
        rows = sorted(groups[k], key=lambda r: (r.get("cap_round") or 0, r.get("stage") or 0))
        head = rows[0]
        ev = "\n".join(
            f"[{r['evidence_id']}] {r['academic_year']} CAP round {r.get('cap_round')} stage {r.get('stage')} | "
            f"{r.get('level_label')} | {r['seat_type']}: closing rank {r['closing_rank']}, "
            f"percentile {r['closing_percentile']}" for r in rows)
        q = (f"What were the closing cutoffs for {head['course_name']} at {head['institute_name']} "
             f"for seat type {head['seat_type']} in {head['academic_year']}?")
        a = ("Historical observation from the supplied records:\n" +
             "\n".join(f"- Round {r.get('cap_round')}, stage {r.get('stage')}: rank {r['closing_rank']}, "
                       f"percentile {r['closing_percentile']} [{r['evidence_id']}]" for r in rows) +
             f"\nThis describes {head['academic_year']} only. It is not a prediction or a guarantee for "
             "any later year; confirm against the official CET Cell notice.")
        examples.append({"messages": [{"role": "system", "content": system},
                                      {"role": "user", "content": f"EVIDENCE:\n{ev}\n\nQUESTION: {q}"},
                                      {"role": "assistant", "content": a}], "type": "grounded"})
    with open(tdir / "sft_grounded_qa.jsonl", "w", encoding="utf-8") as f:
        for e in examples:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return len(flat), len(examples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-sft", type=int, default=20000)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(Path(args.input).rglob("*.pdf"))
    if not pdfs:
        sys.exit("No PDFs found.")
    try:
        from tqdm import tqdm
        it = tqdm(pdfs)
    except ImportError:
        it = pdfs

    inst_cache = {}
    all_records, all_quar, report = [], [], {"files": [], "skipped_unrecognised": [], "warnings": []}
    for p in it:
        try:
            recs, quar, info = parse_pdf(p, inst_cache)
        except Exception as e:
            report["files"].append({"file": str(p), "error": str(e)[:300]})
            continue
        report["files"].append(info)
        if info.get("format") is None:
            report["skipped_unrecognised"].append(str(p))
            continue
        if info.get("year") == "unknown":
            report["warnings"].append(f"{p.name}: year not detected; put PDFs in a year-named folder")
        if info.get("cap_round") is None:
            report["warnings"].append(f"{p.name}: CAP round not detected from title text")
        if info["records"] == 0:
            report["warnings"].append(f"{p.name}: 0 records parsed from a recognised-format file - layout "
                                       "differs from what this script expects, inspect manually")
        all_records += recs
        all_quar += quar

    low_conf = [r.get("course_code") for r in all_records if r.get("name_confidence") == "unverified"]
    report["low_confidence_names"] = {"count": len(low_conf), "sample": low_conf[:20]}
    stripped = [r.get("course_code") for r in all_records if r.get("course_name_note")]
    report["trailing_fragment_stripped"] = {"count": len(stripped), "sample": stripped[:20]}

    years = build_college_files(all_records, out)
    n_rows, n_sft = write_training(all_records, out, args.max_sft)
    with open(out / "quarantine.jsonl", "w", encoding="utf-8") as f:
        for q in all_quar:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    report["summary"] = {"pdfs": len(pdfs), "records": n_rows, "quarantined": len(all_quar),
                         "sft_examples": n_sft, "years": {y: len(c) for y, c in years.items()}}
    (out / "extraction_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    if report["skipped_unrecognised"]:
        print(f"\nSkipped {len(report['skipped_unrecognised'])} file(s) not matching either cutoff "
              f"layout (expected for seat-matrix/vacancy PDFs): {report['skipped_unrecognised']}")
    if low_conf:
        print(f"\n{len(low_conf)} all-India records have unverified institute-name splits - see "
              "extraction_report.json -> low_confidence_names. Excluded from SFT examples but kept "
              "in records_<year>.jsonl with name_confidence='unverified'.")


if __name__ == "__main__":
    main()
