#!/usr/bin/env python3

"""
MHT-CET Engineering CAP Cutoff PDF Extractor
=============================================

TEST VERSION

Designed for:
    - Maharashtra / Minority CAP cutoff PDFs
    - All India (AI) CAP cutoff PDFs

Input:
    AI-con/
        extract_data.py
        Raw_data/
            *.pdf

Output:
    AI-con/
        output/
            json/
                <pdf_name>.json

            jsonl/
                all_records.jsonl

            quarantine/
                quarantine.jsonl

            reports/
                extraction_report.json

The goal of this version is:
    PDF -> structured JSON

We are NOT generating ML/SFT data yet.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber


# ============================================================
# CONFIGURATION
# ============================================================

PARSER_VERSION = "0.2.0-test"

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "RAW_data"
OUTPUT_DIR = BASE_DIR / "output"

JSON_DIR = OUTPUT_DIR / "json"
JSONL_DIR = OUTPUT_DIR / "jsonl"
QUARANTINE_DIR = OUTPUT_DIR / "quarantine"
REPORT_DIR = OUTPUT_DIR / "reports"


# ============================================================
# REGEX
# ============================================================

YEAR_RANGE_RE = re.compile(
    r"(20\d{2})\s*[-_/]\s*(\d{2,4})",
    re.IGNORECASE,
)

YEAR_RE = re.compile(
    r"\b(20\d{2})\b"
)

ROUND_RE = re.compile(
    r"(?:CAP[_\s-]*Round|CAP|Round|Rnd)[_\s-]*(IV|III|II|I|[1-9])",
    re.IGNORECASE,
)

INSTITUTE_RE = re.compile(
    r"^\s*(\d{4,5})\s*[-:–]\s*(.+?)\s*$"
)

COURSE_RE = re.compile(
    r"^\s*(\d{9,10})\s*[-:–]\s*(.+?)\s*$"
)

STATUS_RE = re.compile(
    r"Status\s*:\s*(.*?)(?:\s+Home\s*University\s*:\s*(.*))?$",
    re.IGNORECASE,
)

HOME_UNIVERSITY_RE = re.compile(
    r"Home\s*University\s*:\s*(.+)$",
    re.IGNORECASE,
)

INTAKE_RE = re.compile(
    r"(?:Sanction(?:ed)?\s*)?Intake\s*:?\s*(\d{1,5})",
    re.IGNORECASE,
)

CHOICE_CODE_RE = re.compile(
    r"\b\d{10}\b"
)

INTEGER_RE = re.compile(
    r"^\d{1,8}$"
)

PERCENTILE_RE = re.compile(
    r"^\(?\d{1,3}(?:\.\d+)?\)?$"
)

COMBINED_RE = re.compile(
    r"^(\d{1,8})\((\d{1,3}(?:\.\d+)?)\)$"
)

STAGE_RE = re.compile(
    r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)$",
    re.IGNORECASE,
)


ROMAN = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def roman_to_int(value: str | None) -> int | None:

    if value is None:
        return None

    value = value.strip().upper()

    if value in ROMAN:
        return ROMAN[value]

    if value.isdigit():
        return int(value)

    return None


def normalize_spaces(value: str) -> str:

    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def safe_int(value: str | None) -> int | None:

    if value is None:
        return None

    value = value.strip()

    if not value.isdigit():
        return None

    return int(value)


def safe_float(value: str | None) -> float | None:

    if value is None:
        return None

    value = value.strip()

    value = value.strip("()")

    try:
        return float(value)
    except ValueError:
        return None


# ============================================================
# YEAR / ROUND DETECTION
# ============================================================

def detect_year(path: Path, first_text: str) -> tuple[str | None, str]:

    candidates = [
        ("filename", str(path)),
        ("pdf_header", first_text),
    ]

    for source, text in candidates:

        match = YEAR_RANGE_RE.search(text)

        if match:

            year = int(match.group(1))

            return (
                f"{year}-{(year + 1) % 100:02d}",
                source,
            )

    for source, text in candidates:

        match = YEAR_RE.search(text)

        if match:

            year = int(match.group(1))

            return (
                f"{year}-{(year + 1) % 100:02d}",
                source,
            )

    return None, "not_detected"


def detect_round(path: Path, first_text: str) -> tuple[int | None, str]:

    match = ROUND_RE.search(path.stem)

    if match:

        return (
            roman_to_int(match.group(1)),
            "filename",
        )

    match = ROUND_RE.search(first_text)

    if match:

        return (
            roman_to_int(match.group(1)),
            "pdf_header",
        )

    return None, "not_detected"


# ============================================================
# PDF FORMAT DETECTION
# ============================================================

def detect_pdf_type(first_text: str) -> str:

    text = normalize_spaces(first_text).lower()

    # All India PDF
    if (
        "all india seats" in text
        or "all india merit" in text
        or "jee to ai" in text
    ):
        return "all_india"

    # Maharashtra / Minority PDF
    if (
        "maharashtra & minority seats" in text
        or "maharashtra state seats" in text
        or "state level" in text
    ):
        return "maharashtra"

    return "unknown"


# ============================================================
# WORD / LINE PROCESSING
# ============================================================

def group_words_into_lines(
    words: list[dict[str, Any]],
    tolerance: float = 3.0,
) -> list[list[dict[str, Any]]]:

    words = sorted(
        words,
        key=lambda w: (
            round(float(w["top"]), 2),
            float(w["x0"]),
        ),
    )

    lines: list[list[dict[str, Any]]] = []

    current: list[dict[str, Any]] = []

    current_top: float | None = None

    for word in words:

        top = float(word["top"])

        if current_top is None:

            current = [word]
            current_top = top
            continue

        if abs(top - current_top) <= tolerance:

            current.append(word)

        else:

            current.sort(key=lambda w: float(w["x0"]))

            lines.append(current)

            current = [word]
            current_top = top

    if current:

        current.sort(key=lambda w: float(w["x0"]))

        lines.append(current)

    return lines


def line_text(line: list[dict[str, Any]]) -> str:

    return normalize_spaces(
        " ".join(str(w["text"]) for w in line)
    )


# ============================================================
# MAHARASHTRA FORMAT
# ============================================================

class MaharashtraParser:

    def __init__(
        self,
        pdf_path: Path,
        year: str | None,
        cap_round: int | None,
    ):

        self.pdf_path = pdf_path
        self.year = year
        self.cap_round = cap_round

        self.records: list[dict[str, Any]] = []
        self.quarantine: list[dict[str, Any]] = []

        self.institute_code: str | None = None
        self.institute_name: str | None = None

        self.course_code: str | None = None
        self.course_name: str | None = None

        self.status: str | None = None
        self.home_university: str | None = None

        self.sanction_intake: int | None = None

        self.section_label: str | None = None
        self.section_key: str = "unspecified"

        self.seat_columns: list[tuple[str, float]] = []

        self.pending_stage: int | None = None
        self.pending_cells: dict[str, dict[str, Any]] = {}

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    def reset_institute(self):

        self.course_code = None
        self.course_name = None

        self.status = None
        self.home_university = None

        self.sanction_intake = None

        self.section_label = None
        self.section_key = "unspecified"

        self.seat_columns = []

        self.pending_stage = None
        self.pending_cells = {}

    # --------------------------------------------------------
    # COLUMN ASSIGNMENT
    # --------------------------------------------------------

    def column_tolerance(self) -> float:

        if len(self.seat_columns) < 2:
            return 40.0

        positions = sorted(
            x for _, x in self.seat_columns
        )

        gaps = [
            b - a
            for a, b in zip(positions, positions[1:])
        ]

        if not gaps:
            return 40.0

        return max(
            12.0,
            min(gaps) * 0.55,
        )

    def assign_column(
        self,
        word: dict[str, Any],
    ) -> str | None:

        if not self.seat_columns:
            return None

        x_center = (
            float(word["x0"]) +
            float(word["x1"])
        ) / 2

        column, column_x = min(
            self.seat_columns,
            key=lambda item: abs(item[1] - x_center),
        )

        if abs(column_x - x_center) <= self.column_tolerance():

            return column

        return None

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    def add_record(
        self,
        seat_type: str,
        rank: int | None,
        percentile: float | None,
        page_number: int,
    ):

        record = {
            "record_id": None,

            "record_type": "maharashtra_cutoff",

            "academic_year": self.year,
            "cap_round": self.cap_round,

            "institute": {
                "code": self.institute_code,
                "name": self.institute_name,
            },

            "course": {
                "choice_code": self.course_code,
                "name": self.course_name,
            },

            "admission": {
                "section": self.section_key,
                "section_label": self.section_label,
                "seat_type": seat_type,
                "stage": self.pending_stage,
            },

            "cutoff": {
                "closing_rank": rank,
                "closing_percentile": percentile,
            },

            "institute_details": {
                "status": self.status,
                "home_university": self.home_university,
                "sanction_intake": self.sanction_intake,
            },

            "source": {
                "file": self.pdf_path.name,
                "page": page_number,
            },

            "parser": {
                "version": PARSER_VERSION,
                "extraction_method": "pdfplumber_coordinates",
            },
        }

        problems = []

        if not self.institute_code:
            problems.append("missing_institute_code")

        if not self.course_code:
            problems.append("missing_course_code")

        if not seat_type:
            problems.append("missing_seat_type")

        if rank is None and percentile is None:
            problems.append("missing_cutoff")

        if rank is not None and rank <= 0:
            problems.append("invalid_rank")

        if percentile is not None and not 0 <= percentile <= 100:
            problems.append("invalid_percentile")

        if problems:

            record["validation"] = {
                "status": "quarantine",
                "problems": problems,
            }

            self.quarantine.append(record)

        else:

            record["validation"] = {
                "status": "valid",
                "problems": [],
            }

            record["record_id"] = self.make_record_id(
                record
            )

            self.records.append(record)

    # --------------------------------------------------------
    # RECORD ID
    # --------------------------------------------------------

    def make_record_id(
        self,
        record: dict[str, Any],
    ) -> str:

        institute = record["institute"]["code"] or "UNKNOWN"
        course = record["course"]["choice_code"] or "UNKNOWN"
        admission = record["admission"]

        seat = admission["seat_type"]
        stage = admission["stage"]

        return (
            f"MH:"
            f"{self.year}:"
            f"R{self.cap_round}:"
            f"{institute}:"
            f"{course}:"
            f"{admission['section']}:"
            f"{seat}:"
            f"S{stage}"
        )

    # --------------------------------------------------------
    # FLUSH
    # --------------------------------------------------------

    def flush_pending(
        self,
        page_number: int,
    ):

        if not self.pending_cells:
            return

        for seat_type, values in self.pending_cells.items():

            self.add_record(
                seat_type=seat_type,
                rank=values.get("rank"),
                percentile=values.get("percentile"),
                page_number=page_number,
            )

        self.pending_stage = None
        self.pending_cells = {}

    # --------------------------------------------------------
    # PARSE PAGE
    # --------------------------------------------------------

    def parse_page(
        self,
        page,
        page_number: int,
    ) -> int:

        words = page.extract_words(
            x_tolerance=2,
            y_tolerance=3,
            keep_blank_chars=False,
        )

        if not words:
            return 0

        lines = group_words_into_lines(words)

        records_before = len(self.records)

        for line in lines:

            texts = [
                str(w["text"])
                for w in line
            ]

            if not texts:
                continue

            text = line_text(line)
            low = text.lower()

            # ------------------------------------------------
            # Course
            # ------------------------------------------------

            match = COURSE_RE.match(text)

            if match:

                self.flush_pending(page_number)

                self.course_code = match.group(1)

                course_name = match.group(2)

                course_name = re.split(
                    r"\s+Status\s*:",
                    course_name,
                    flags=re.IGNORECASE,
                )[0]

                self.course_name = normalize_spaces(
                    course_name
                )

                self.status = None
                self.home_university = None
                self.sanction_intake = None

                continue

            # ------------------------------------------------
            # Institute
            # ------------------------------------------------

            match = INSTITUTE_RE.match(text)

            if match and not COURSE_RE.match(text):

                self.flush_pending(page_number)

                self.institute_code = match.group(1)

                self.institute_name = normalize_spaces(
                    match.group(2)
                )

                self.reset_institute()

                continue

            # ------------------------------------------------
            # Status
            # ------------------------------------------------

            if low.startswith("status"):

                match = STATUS_RE.search(text)

                if match:

                    self.status = (
                        normalize_spaces(match.group(1))
                        if match.group(1)
                        else self.status
                    )

                    if match.group(2):

                        self.home_university = normalize_spaces(
                            match.group(2)
                        )

                continue

            # ------------------------------------------------
            # Home University
            # ------------------------------------------------

            match = HOME_UNIVERSITY_RE.search(text)

            if match:

                self.home_university = normalize_spaces(
                    match.group(1)
                )

                continue

            # ------------------------------------------------
            # Intake
            # ------------------------------------------------

            match = INTAKE_RE.search(text)

            if match and self.course_code:

                self.sanction_intake = int(
                    match.group(1)
                )

                continue

            # ------------------------------------------------
            # Section labels
            # ------------------------------------------------

            section_patterns = [
                "state level",
                "home university seats allotted",
                "other than home university seats allotted",
                "all india seats",
            ]

            if any(
                pattern in low
                for pattern in section_patterns
            ):

                self.flush_pending(page_number)

                self.section_label = text
                self.section_key = slugify(text)

                continue

            # ------------------------------------------------
            # Seat-type header
            #
            # Example:
            #
            # GOPENS GSCS GSTS GVJS ...
            # ------------------------------------------------

            if (
                len(line) >= 2
                and texts[0].lower() == "stage"
            ):

                self.flush_pending(page_number)

                self.seat_columns = [
                    (
                        str(word["text"]).strip(),
                        (
                            float(word["x0"]) +
                            float(word["x1"])
                        ) / 2,
                    )
                    for word in line[1:]
                ]

                continue

            # ------------------------------------------------
            # Sometimes Stage header can be split.
            # Detect lines that look like seat categories.
            # ------------------------------------------------

            if self.looks_like_seat_header(texts):

                self.flush_pending(page_number)

                self.seat_columns = [
                    (
                        str(word["text"]).strip(),
                        (
                            float(word["x0"]) +
                            float(word["x1"])
                        ) / 2,
                    )
                    for word in line
                ]

                continue

            # ------------------------------------------------
            # Percentile row
            # ------------------------------------------------

            if (
                self.pending_cells
                and self.seat_columns
                and self.is_percentile_row(texts)
            ):

                for word in line:

                    column = self.assign_column(word)

                    if (
                        column
                        and column in self.pending_cells
                    ):

                        value = safe_float(
                            str(word["text"])
                        )

                        self.pending_cells[
                            column
                        ]["percentile"] = value

                self.flush_pending(page_number)

                continue

            # ------------------------------------------------
            # New line means pending rank should be flushed
            # unless this line is percentile continuation.
            # ------------------------------------------------

            if self.pending_cells:

                self.flush_pending(page_number)

            # ------------------------------------------------
            # Rank row
            #
            # I 37591
            # (88.9550679)
            #
            # OR
            #
            # I 37591(88.9550679)
            # ------------------------------------------------

            if (
                self.seat_columns
                and texts
                and STAGE_RE.match(texts[0])
            ):

                stage = roman_to_int(texts[0])

                cells: dict[str, dict[str, Any]] = {}

                for word in line[1:]:

                    token = str(word["text"]).strip()

                    column = self.assign_column(word)

                    if not column:
                        continue

                    combined = COMBINED_RE.match(token)

                    if combined:

                        cells[column] = {
                            "rank": int(
                                combined.group(1)
                            ),
                            "percentile": float(
                                combined.group(2)
                            ),
                        }

                        continue

                    if INTEGER_RE.match(token):

                        cells[column] = {
                            "rank": int(token)
                        }

                if cells:

                    self.pending_stage = stage
                    self.pending_cells = cells

                    continue

        self.flush_pending(page_number)

        return len(self.records) - records_before

    # --------------------------------------------------------
    # SEAT HEADER DETECTION
    # --------------------------------------------------------

    @staticmethod
    def looks_like_seat_header(
        texts: list[str],
    ) -> bool:

        if len(texts) < 2:
            return False

        valid = 0

        for token in texts:

            token = token.strip()

            if re.match(
                r"^[GL][A-Z0-9]+[A-Z]$",
                token,
                re.IGNORECASE,
            ):
                valid += 1

            elif token.upper() in {
                "TFWS",
                "EWS",
                "ORPHAN",
            }:
                valid += 1

        return valid >= 2

    @staticmethod
    def is_percentile_row(
        texts: list[str],
    ) -> bool:

        if not texts:
            return False

        valid = 0

        for token in texts:

            token = token.strip()

            if PERCENTILE_RE.match(token):

                value = safe_float(token)

                if value is not None and 0 <= value <= 100:

                    valid += 1

        return valid >= 1

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    def parse(self) -> tuple[list[dict], list[dict], dict]:

        info = {
            "file": self.pdf_path.name,
            "format": "maharashtra",
            "pages": 0,
            "pages_without_text": 0,
            "records": 0,
            "quarantined": 0,
        }

        with pdfplumber.open(self.pdf_path) as pdf:

            info["pages"] = len(pdf.pages)

            for page_number, page in enumerate(
                pdf.pages,
                start=1,
            ):

                try:

                    words = page.extract_words(
                        x_tolerance=2,
                        y_tolerance=3,
                    )

                    if not words:

                        info["pages_without_text"] += 1

                        continue

                    self.parse_page(
                        page,
                        page_number,
                    )

                except Exception as exc:

                    self.quarantine.append(
                        {
                            "record_type": "page_error",
                            "source": {
                                "file": self.pdf_path.name,
                                "page": page_number,
                            },
                            "error": str(exc),
                        }
                    )

        info["records"] = len(self.records)
        info["quarantined"] = len(self.quarantine)

        return (
            self.records,
            self.quarantine,
            info,
        )


# ============================================================
# ALL INDIA FORMAT
# ============================================================

class AllIndiaParser:

    def __init__(
        self,
        pdf_path: Path,
        year: str | None,
        cap_round: int | None,
    ):

        self.pdf_path = pdf_path
        self.year = year
        self.cap_round = cap_round

        self.records: list[dict[str, Any]] = []
        self.quarantine: list[dict[str, Any]] = []

    # --------------------------------------------------------
    # CREATE RECORD
    # --------------------------------------------------------

    def create_record(
        self,
        institute_code: str | None,
        institute_name: str | None,
        serial_number: int | None,
        merit_rank: int | None,
        percentile: float | None,
        choice_code: str | None,
        seat_type: str | None,
        course_name: str | None,
        merit_exam: str | None,
        page_number: int,
    ) -> None:

        record = {
            "record_id": None,

            "record_type": "all_india_cutoff",

            "academic_year": self.year,
            "cap_round": self.cap_round,

            "institute": {
                "code": institute_code,
                "name": institute_name,
            },

            "course": {
                "choice_code": choice_code,
                "name": course_name,
            },

            "admission": {
                "section": "all_india",
                "section_label": "All India Seats",
                "seat_type": seat_type,
            },

            "cutoff": {
                "closing_rank": merit_rank,
                "closing_percentile": percentile,
            },

            "all_india": {
                "serial_number": serial_number,
                "merit_exam": merit_exam,
            },

            "source": {
                "file": self.pdf_path.name,
                "page": page_number,
            },

            "parser": {
                "version": PARSER_VERSION,
                "extraction_method": "pdfplumber_text",
            },
        }

        problems = []

        if not institute_name:
            problems.append("missing_institute_name")

        if not choice_code:
            problems.append("missing_choice_code")

        if merit_rank is None:
            problems.append("missing_merit_rank")

        if percentile is None:
            problems.append("missing_score_or_percentile")

        if percentile is not None and not 0 <= percentile <= 100:
            problems.append("invalid_score_or_percentile")

        if problems:

            record["validation"] = {
                "status": "quarantine",
                "problems": problems,
            }

            self.quarantine.append(record)

            return

        record["record_id"] = (
            f"AI:"
            f"{self.year}:"
            f"R{self.cap_round}:"
            f"{institute_code or 'UNKNOWN'}:"
            f"{choice_code}:"
            f"{seat_type or 'UNKNOWN'}"
        )

        record["validation"] = {
            "status": "valid",
            "problems": [],
        }

        self.records.append(record)

    # --------------------------------------------------------
    # PARSE
    # --------------------------------------------------------

    def parse(self) -> tuple[list[dict], list[dict], dict]:

        info = {
            "file": self.pdf_path.name,
            "format": "all_india",
            "pages": 0,
            "pages_without_text": 0,
            "records": 0,
            "quarantined": 0,
        }

        current_institute_code = None
        current_institute_name = None

        with pdfplumber.open(self.pdf_path) as pdf:

            info["pages"] = len(pdf.pages)

            for page_number, page in enumerate(
                pdf.pages,
                start=1,
            ):

                text = page.extract_text() or ""

                if not text.strip():

                    info["pages_without_text"] += 1

                    continue

                lines = [
                    normalize_spaces(line)
                    for line in text.splitlines()
                ]

                i = 0

                while i < len(lines):

                    line = lines[i]

                    # ------------------------------------------------
                    # Institute
                    #
                    # 01101 - Shri Sant Gajanan Maharaj College...
                    # ------------------------------------------------

                    institute_match = re.match(
                        r"^(\d{4,5})\s*-\s*(.+)$",
                        line,
                    )

                    if institute_match:

                        current_institute_code = (
                            institute_match.group(1)
                        )

                        current_institute_name = (
                            institute_match.group(2).strip()
                        )

                        # Institute name may continue on next line.
                        j = i + 1

                        while (
                            j < len(lines)
                            and lines[j]
                            and not CHOICE_CODE_RE.search(lines[j])
                            and not re.match(
                                r"^\d+\s+\d+\s+\(",
                                lines[j],
                            )
                            and not re.match(
                                r"^\d{4,5}\s*-\s*",
                                lines[j],
                            )
                            and "page " not in lines[j].lower()
                        ):

                            # Stop if it looks like a PDF header.
                            if (
                                "cut off list" in lines[j].lower()
                                or "state common entrance" in lines[j].lower()
                            ):
                                break

                            current_institute_name += (
                                " " + lines[j]
                            )

                            j += 1

                        i += 1

                    # ------------------------------------------------
                    # Record detection
                    #
                    # Example:
                    #
                    # 1 15312 (86.6844102)
                    # 0110124210 AI AI JEE to AI Computer Science...
                    # ------------------------------------------------

                    record_match = re.match(
                        r"^(\d+)\s+(\d+)\s+\(([\d.]+)\)\s*$",
                        line,
                    )

                    if record_match:

                        serial_number = int(
                            record_match.group(1)
                        )

                        merit_rank = int(
                            record_match.group(2)
                        )

                        score = float(
                            record_match.group(3)
                        )

                        # The choice-code line normally follows.
                        choice_line = ""

                        if i + 1 < len(lines):

                            choice_line = lines[i + 1]

                        choice_match = CHOICE_CODE_RE.search(
                            choice_line
                        )

                        if not choice_match:

                            self.quarantine.append(
                                {
                                    "record_type": "all_india_row",
                                    "source": {
                                        "file": self.pdf_path.name,
                                        "page": page_number,
                                    },
                                    "raw_line": line,
                                    "reason": "choice_code_not_found",
                                }
                            )

                            i += 1
                            continue

                        choice_code = choice_match.group(0)

                        before_code = normalize_spaces(
                            choice_line[
                                :choice_match.start()
                            ]
                        )

                        after_code = normalize_spaces(
                            choice_line[
                                choice_match.end():
                            ]
                        )

                        # ------------------------------------------------
                        # Usually:
                        #
                        # AI AI JEE to AI Computer Science...
                        #
                        # ------------------------------------------------

                        tokens = after_code.split()

                        seat_type = None
                        merit_exam = None
                        course_parts: list[str] = []

                        if tokens:

                            # First AI = type
                            # Second AI = seat type
                            # Everything after "JEE to AI"
                            # is course.
                            #
                            # We keep the parser conservative.

                            if tokens[0].upper() == "AI":

                                seat_type = "AI"

                            marker_index = -1

                            for idx, token in enumerate(tokens):

                                if token.lower() == "to":
                                    marker_index = idx

                            if marker_index >= 0:

                                exam_tokens = tokens[
                                    :marker_index
                                ]

                                merit_exam = normalize_spaces(
                                    " ".join(exam_tokens)
                                )

                                course_parts = tokens[
                                    marker_index + 1:
                                ]

                            else:

                                course_parts = tokens

                        course_name = normalize_spaces(
                            " ".join(course_parts)
                        )

                        # Course name can continue onto next line.
                        j = i + 2

                        while (
                            j < len(lines)
                            and lines[j]
                            and not re.match(
                                r"^\d+\s+\d+\s+\(",
                                lines[j],
                            )
                            and not re.match(
                                r"^\d{4,5}\s*-\s*",
                                lines[j],
                            )
                            and "page " not in lines[j].lower()
                        ):

                            # Don't accidentally include footer/header.
                            lower = lines[j].lower()

                            if (
                                "cut off indicates" in lower
                                or "state common entrance" in lower
                                or "choice code" in lower
                            ):
                                break

                            # If another choice code appears,
                            # current course is complete.
                            if CHOICE_CODE_RE.search(lines[j]):

                                break

                            course_name = normalize_spaces(
                                course_name + " " + lines[j]
                            )

                            j += 1

                        self.create_record(
                            institute_code=current_institute_code,
                            institute_name=current_institute_name,
                            serial_number=serial_number,
                            merit_rank=merit_rank,
                            percentile=score,
                            choice_code=choice_code,
                            seat_type=seat_type,
                            course_name=course_name,
                            merit_exam=merit_exam,
                            page_number=page_number,
                        )

                        i += 1

                    i += 1

        info["records"] = len(self.records)
        info["quarantined"] = len(self.quarantine)

        return (
            self.records,
            self.quarantine,
            info,
        )


# ============================================================
# WRITE JSON
# ============================================================

def write_json(
    path: Path,
    data: Any,
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_jsonl(
    path: Path,
    records: list[dict[str, Any]],
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:

        for record in records:

            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )


# ============================================================
# PROCESS ONE PDF
# ============================================================

def process_pdf(
    pdf_path: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:

    print()
    print("=" * 80)
    print(f"Processing: {pdf_path.name}")
    print("=" * 80)

    with pdfplumber.open(pdf_path) as pdf:

        first_text = (
            pdf.pages[0].extract_text() or ""
            if pdf.pages
            else ""
        )

    year, year_source = detect_year(
        pdf_path,
        first_text,
    )

    cap_round, round_source = detect_round(
        pdf_path,
        first_text,
    )

    pdf_type = detect_pdf_type(
        first_text
    )

    print(f"Format       : {pdf_type}")
    print(f"Academic Year: {year}")
    print(f"CAP Round    : {cap_round}")
    print(f"Year Source  : {year_source}")
    print(f"Round Source : {round_source}")

    if pdf_type == "maharashtra":

        parser = MaharashtraParser(
            pdf_path,
            year,
            cap_round,
        )

    elif pdf_type == "all_india":

        parser = AllIndiaParser(
            pdf_path,
            year,
            cap_round,
        )

    else:

        return (
            [],
            [
                {
                    "record_type": "file",
                    "source": {
                        "file": pdf_path.name,
                    },
                    "reason": "unknown_pdf_format",
                }
            ],
            {
                "file": pdf_path.name,
                "format": "unknown",
                "year": year,
                "cap_round": cap_round,
                "pages": 0,
                "records": 0,
                "quarantined": 1,
            },
        )

    records, quarantine, info = parser.parse()

    info.update(
        {
            "academic_year": year,
            "year_detection_source": year_source,
            "cap_round": cap_round,
            "round_detection_source": round_source,
            "sha256": sha256_file(pdf_path),
            "processed_at": now_utc(),
            "parser_version": PARSER_VERSION,
        }
    )

    print(f"Records      : {len(records)}")
    print(f"Quarantine   : {len(quarantine)}")

    return (
        records,
        quarantine,
        info,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("MHT-CET CAP CUTOFF EXTRACTOR")
    print(f"Parser version: {PARSER_VERSION}")
    print()

    if not RAW_DIR.exists():

        print(
            f"ERROR: Raw_data folder not found:\n"
            f"{RAW_DIR}"
        )

        sys.exit(1)

    pdf_files = sorted(
        RAW_DIR.rglob("*.pdf")
    )

    if not pdf_files:

        print(
            f"ERROR: No PDF files found in:\n"
            f"{RAW_DIR}"
        )

        sys.exit(1)

    print(
        f"Found {len(pdf_files)} PDF files."
    )

    JSON_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    JSONL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    QUARANTINE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_records: list[dict[str, Any]] = []
    all_quarantine: list[dict[str, Any]] = []

    report = {
        "parser_version": PARSER_VERSION,
        "started_at": now_utc(),
        "input_directory": str(RAW_DIR),
        "files": [],
        "summary": {},
    }

    # --------------------------------------------------------
    # PROCESS ALL PDFs
    # --------------------------------------------------------

    for pdf_path in pdf_files:

        try:

            records, quarantine, info = process_pdf(
                pdf_path
            )

            all_records.extend(records)
            all_quarantine.extend(quarantine)

            report["files"].append(info)

            # ------------------------------------------------
            # One JSON per source PDF
            # ------------------------------------------------

            output_name = (
                slugify(pdf_path.stem)
                + ".json"
            )

            pdf_output = {
                "metadata": {
                    "source_file": pdf_path.name,
                    "academic_year": info.get(
                        "academic_year"
                    ),
                    "cap_round": info.get(
                        "cap_round"
                    ),
                    "format": info.get(
                        "format"
                    ),
                    "parser_version": PARSER_VERSION,
                    "processed_at": now_utc(),
                    "sha256": info.get(
                        "sha256"
                    ),
                },

                "statistics": {
                    "records": len(records),
                    "quarantined": len(quarantine),
                },

                "records": records,
            }

            write_json(
                JSON_DIR / output_name,
                pdf_output,
            )

            print(
                f"JSON saved: "
                f"output/json/{output_name}"
            )

        except Exception as exc:

            print(
                f"ERROR processing "
                f"{pdf_path.name}: {exc}"
            )

            report["files"].append(
                {
                    "file": pdf_path.name,
                    "error": str(exc),
                }
            )

    # --------------------------------------------------------
    # ALL RECORDS JSONL
    # --------------------------------------------------------

    write_jsonl(
        JSONL_DIR / "all_records.jsonl",
        all_records,
    )

    # --------------------------------------------------------
    # ALL RECORDS JSON
    # --------------------------------------------------------

    write_json(
        JSONL_DIR / "all_records.json",
        {
            "metadata": {
                "parser_version": PARSER_VERSION,
                "generated_at": now_utc(),
                "record_count": len(all_records),
            },
            "records": all_records,
        },
    )

    # --------------------------------------------------------
    # QUARANTINE
    # --------------------------------------------------------

    write_jsonl(
        QUARANTINE_DIR / "quarantine.jsonl",
        all_quarantine,
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    formats = defaultdict(int)
    years = defaultdict(int)
    rounds = defaultdict(int)

    for info in report["files"]:

        formats[str(
            info.get("format")
        )] += 1

        years[str(
            info.get("academic_year")
        )] += 1

        rounds[str(
            info.get("cap_round")
        )] += 1

    report["summary"] = {
        "pdf_count": len(pdf_files),
        "successful_files": len(
            [
                x
                for x in report["files"]
                if "error" not in x
            ]
        ),
        "record_count": len(all_records),
        "quarantine_count": len(
            all_quarantine
        ),
        "formats": dict(formats),
        "years": dict(years),
        "rounds": dict(rounds),
    }

    report["finished_at"] = now_utc()

    write_json(
        REPORT_DIR / "extraction_report.json",
        report,
    )

    # --------------------------------------------------------
    # CONSOLE SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)

    print(
        f"PDF files       : "
        f"{len(pdf_files)}"
    )

    print(
        f"Total records   : "
        f"{len(all_records)}"
    )

    print(
        f"Quarantined     : "
        f"{len(all_quarantine)}"
    )

    print()
    print("Formats:")

    for key, value in formats.items():

        print(
            f"  {key}: {value}"
        )

    print()
    print("Academic Years:")

    for key, value in years.items():

        print(
            f"  {key}: {value} PDF(s)"
        )

    print()
    print("CAP Rounds:")

    for key, value in rounds.items():

        print(
            f"  Round {key}: {value} PDF(s)"
        )

    print()
    print(
        "Output directory:"
    )

    print(
        OUTPUT_DIR
    )

    print()
    print(
        "Next important step:"
    )

    print(
        "Open output/reports/extraction_report.json "
        "and inspect output/json/*.json"
    )

    print()


if __name__ == "__main__":
    main()