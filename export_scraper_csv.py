#!/usr/bin/env python3

import csv
import json
import re
import shutil
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

INPUT_DIR = Path("scraper_output")
JSON_DIR = INPUT_DIR / "json"
CSV_DIR = INPUT_DIR / "csv"

JSON_DIR.mkdir(parents=True, exist_ok=True)
CSV_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# HELPERS
# ============================================================

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] {path}: {e}")
        return None


def to_json(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":")
        )

    return str(value)


def to_text(value):
    if value is None:
        return ""

    if isinstance(value, list):
        return ", ".join(str(x) for x in value)

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def write_csv(path, rows, fields):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
            extrasaction="ignore"
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(row)


def get_json_files():
    return sorted(
        p for p in INPUT_DIR.glob("*.json")
        if p.name != "run_metadata.json"
    )


# ============================================================
# GENERIC EVIDENCE FLATTENER
# ============================================================

def flatten_evidence(
    obj,
    institute_code,
    institute_name,
    section,
    field_path="",
    inherited=None,
    rows=None,
):
    """
    Converts nested extracted/historical JSON information
    into normalized evidence rows.

    Important:
    Nothing is intentionally discarded.
    """

    if rows is None:
        rows = []

    if inherited is None:
        inherited = {}

    # --------------------------------------------------------
    # DICTIONARY
    # --------------------------------------------------------

    if isinstance(obj, dict):

        current_meta = dict(inherited)

        # Common evidence metadata
        for key in (
            "source_url",
            "source_type",
            "context",
            "confidence",
            "years_mentioned",
            "year",
        ):
            if key in obj:
                current_meta[key] = obj[key]

        # Evidence object
        if "value" in obj:

            rows.append({
                "institute_code": institute_code,
                "institute_name": institute_name,
                "section": section,
                "field": field_path,
                "value": to_text(obj.get("value")),
                "kind": to_text(obj.get("kind")),
                "year": to_text(obj.get("year")),
                "years_mentioned": to_text(
                    obj.get("years_mentioned")
                ),
                "source_url": to_text(
                    obj.get(
                        "source_url",
                        current_meta.get("source_url", "")
                    )
                ),
                "source_type": to_text(
                    obj.get(
                        "source_type",
                        current_meta.get("source_type", "")
                    )
                ),
                "confidence": to_text(
                    obj.get(
                        "confidence",
                        current_meta.get("confidence", "")
                    )
                ),
                "context": to_text(
                    obj.get(
                        "context",
                        current_meta.get("context", "")
                    )
                ),
            })

            # Also inspect other nested fields
            for key, value in obj.items():

                if key in {
                    "value",
                    "kind",
                    "source_url",
                    "source_type",
                    "context",
                    "confidence",
                    "years_mentioned",
                    "year",
                }:
                    continue

                new_path = (
                    f"{field_path}.{key}"
                    if field_path
                    else key
                )

                flatten_evidence(
                    value,
                    institute_code,
                    institute_name,
                    section,
                    new_path,
                    current_meta,
                    rows,
                )

            return rows

        # Normal dictionary
        for key, value in obj.items():

            new_path = (
                f"{field_path}.{key}"
                if field_path
                else key
            )

            flatten_evidence(
                value,
                institute_code,
                institute_name,
                section,
                new_path,
                current_meta,
                rows,
            )

        return rows

    # --------------------------------------------------------
    # LIST
    # --------------------------------------------------------

    if isinstance(obj, list):

        for i, value in enumerate(obj):

            new_path = (
                f"{field_path}[{i}]"
                if field_path
                else f"[{i}]"
            )

            flatten_evidence(
                value,
                institute_code,
                institute_name,
                section,
                new_path,
                inherited,
                rows,
            )

        return rows

    # --------------------------------------------------------
    # SIMPLE VALUE
    # --------------------------------------------------------

    rows.append({
        "institute_code": institute_code,
        "institute_name": institute_name,
        "section": section,
        "field": field_path,
        "value": to_text(obj),
        "kind": "",
        "year": "",
        "years_mentioned": "",
        "source_url": to_text(
            inherited.get("source_url", "")
        ),
        "source_type": to_text(
            inherited.get("source_type", "")
        ),
        "confidence": to_text(
            inherited.get("confidence", "")
        ),
        "context": to_text(
            inherited.get("context", "")
        ),
    })

    return rows


# ============================================================
# COLLEGE OVERVIEW
# ============================================================

def make_college_row(data):

    extracted = data.get("extracted", {})
    crawl = data.get("crawl", {})
    contact = extracted.get("contact", {})

    if not isinstance(contact, dict):
        contact = {}

    return {
        "institute_code": data.get("institute_code", ""),
        "institute_name": data.get("institute_name", ""),
        "official_url": data.get("url", ""),
        "url_source": data.get("url_source", ""),
        "scraped_at": data.get("scraped_at", ""),
        "status": data.get("status", ""),

        "established_year": to_json(
            extracted.get("established_year", [])
        ),

        "affiliation": to_json(
            extracted.get("affiliation", [])
        ),

        "naac": to_json(
            extracted.get("naac", [])
        ),

        "nba": to_json(
            extracted.get("nba", [])
        ),

        "nirf": to_json(
            extracted.get("nirf", [])
        ),

        "fees": to_json(
            extracted.get("fees", [])
        ),

        "placements": to_json(
            extracted.get("placement_mentions", [])
        ),

        "recruiters": to_json(
            extracted.get("recruiter_mentions", [])
        ),

        "admissions": to_json(
            extracted.get("admission_mentions", [])
        ),

        "approvals": to_json(
            extracted.get("approval_mentions", [])
        ),

        "rankings": to_json(
            extracted.get("ranking_mentions", [])
        ),

        "contact_mentions": to_json(
            extracted.get("contact_mentions", [])
        ),

        "emails": to_json(
            contact.get("emails", [])
        ),

        "phones": to_json(
            contact.get("phones", [])
        ),

        "address": to_json(
            contact.get("address", "")
        ),

        "historical": to_json(
            data.get("historical", {})
        ),

        "documents": to_json(
            data.get("documents", {})
        ),

        "quality": to_json(
            data.get("quality", {})
        ),

        "pages_crawled": len(
            crawl.get("pages_crawled", [])
        ),

        "pdf_count": crawl.get(
            "pdf_count",
            0
        ),

        "crawl_errors": to_json(
            crawl.get("errors", [])
        ),
    }


# ============================================================
# SPECIALIZED CSV RECORDS
# ============================================================

def evidence_list(value):
    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return [value]

    return []


def make_special_rows(
    data,
    field_name,
):
    """
    Extract a specific list such as:
    placement_mentions
    recruiter_mentions
    admission_mentions
    approval_mentions
    ranking_mentions
    fees
    """

    rows = []

    institute_code = data.get("institute_code", "")
    institute_name = data.get("institute_name", "")

    extracted = data.get("extracted", {})

    items = evidence_list(
        extracted.get(field_name, [])
    )

    for i, item in enumerate(items, start=1):

        if isinstance(item, dict):

            rows.append({
                "institute_code": institute_code,
                "institute_name": institute_name,
                "record_number": i,
                "value": to_text(item.get("value")),
                "kind": to_text(item.get("kind")),
                "year": to_text(item.get("year")),
                "years_mentioned": to_text(
                    item.get("years_mentioned")
                ),
                "source_url": to_text(
                    item.get("source_url")
                ),
                "source_type": to_text(
                    item.get("source_type")
                ),
                "confidence": to_text(
                    item.get("confidence")
                ),
                "context": to_text(
                    item.get("context")
                ),
            })

        else:

            rows.append({
                "institute_code": institute_code,
                "institute_name": institute_name,
                "record_number": i,
                "value": to_text(item),
                "kind": "",
                "year": "",
                "years_mentioned": "",
                "source_url": "",
                "source_type": "",
                "confidence": "",
                "context": "",
            })

    return rows


# ============================================================
# PLACEMENT EXTRACTION
# ============================================================

def extract_package(value, context):

    text = f"{value} {context}"

    patterns = [
        r"(\d+(?:\.\d+)?)\s*LPA",
        r"₹\s*(\d+(?:\.\d+)?)\s*(?:LPA)?",
        r"(?:Rs\.?|INR)\s*(\d+(?:\.\d+)?)\s*(?:LPA)?",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            return match.group(1)

    return ""


def extract_company(context):

    patterns = [
        r"selected in\s+(.+?)\s+with a package",
        r"selected in\s+(.+?)\s+Package",
        r"Selected in\s+(.+?)\s+with a package",
        r"Selected in\s+(.+?)\s+Package",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            context,
            flags=re.IGNORECASE
        )

        if match:
            company = match.group(1).strip()

            company = re.sub(
                r"\s+,\s*$",
                "",
                company
            )

            return company

    return ""


def make_placement_rows(data):

    base_rows = make_special_rows(
        data,
        "placement_mentions"
    )

    for row in base_rows:

        row["company"] = extract_company(
            row["context"]
        )

        row["package_lpa"] = extract_package(
            row["value"],
            row["context"]
        )

    return base_rows


# ============================================================
# CONTACT CSV
# ============================================================

def make_contact_rows(data):

    rows = []

    institute_code = data.get(
        "institute_code",
        ""
    )

    institute_name = data.get(
        "institute_name",
        ""
    )

    contact = data.get(
        "extracted",
        {}
    ).get(
        "contact",
        {}
    )

    if not isinstance(contact, dict):
        return rows

    for email in contact.get("emails", []):

        rows.append({
            "institute_code": institute_code,
            "institute_name": institute_name,
            "contact_type": "email",
            "value": str(email),
        })

    for phone in contact.get("phones", []):

        rows.append({
            "institute_code": institute_code,
            "institute_name": institute_name,
            "contact_type": "phone",
            "value": str(phone),
        })

    address = contact.get(
        "address",
        ""
    )

    if address:

        rows.append({
            "institute_code": institute_code,
            "institute_name": institute_name,
            "contact_type": "address",
            "value": str(address),
        })

    return rows


# ============================================================
# PAGE CSV
# ============================================================

def make_page_rows(data):

    rows = []

    institute_code = data.get(
        "institute_code",
        ""
    )

    institute_name = data.get(
        "institute_name",
        ""
    )

    pages = data.get(
        "raw_text_pages",
        []
    )

    if isinstance(pages, dict):

        pages = [
            {
                "key": key,
                "data": value
            }
            for key, value in pages.items()
        ]

    if not isinstance(pages, list):
        return rows

    for i, page in enumerate(
        pages,
        start=1
    ):

        if isinstance(page, dict):

            url = (
                page.get("url")
                or page.get("source_url")
                or page.get("page_url")
                or ""
            )

            title = (
                page.get("title")
                or ""
            )

            text = (
                page.get("text")
                or page.get("content")
                or page.get("raw_text")
                or ""
            )

            status = page.get(
                "status",
                ""
            )

            metadata = page

        else:

            url = ""
            title = ""
            text = str(page)
            status = ""
            metadata = {}

        rows.append({
            "institute_code": institute_code,
            "institute_name": institute_name,
            "page_number": i,
            "url": url,
            "title": title,
            "status": status,
            "text": text,
            "metadata": to_json(metadata),
        })

    return rows


# ============================================================
# PDF / DOCUMENT CSV
# ============================================================

def make_document_rows(data):

    rows = []

    institute_code = data.get(
        "institute_code",
        ""
    )

    institute_name = data.get(
        "institute_name",
        ""
    )

    documents = data.get(
        "documents",
        []
    )

    if isinstance(documents, dict):

        documents = [
            {
                "document_key": key,
                "data": value
            }
            for key, value in documents.items()
        ]

    if not isinstance(documents, list):
        documents = []

    for i, doc in enumerate(
        documents,
        start=1
    ):

        if isinstance(doc, dict):

            rows.append({
                "institute_code": institute_code,
                "institute_name": institute_name,
                "document_number": i,
                "url": doc.get(
                    "url",
                    doc.get(
                        "source_url",
                        ""
                    )
                ),
                "filename": doc.get(
                    "filename",
                    ""
                ),
                "title": doc.get(
                    "title",
                    ""
                ),
                "year": doc.get(
                    "year",
                    ""
                ),
                "source_type": doc.get(
                    "source_type",
                    "pdf"
                ),
                "page_count": doc.get(
                    "page_count",
                    ""
                ),
                "text": to_text(
                    doc.get(
                        "text",
                        doc.get(
                            "content",
                            ""
                        )
                    )
                ),
                "metadata": to_json(doc),
            })

        else:

            rows.append({
                "institute_code": institute_code,
                "institute_name": institute_name,
                "document_number": i,
                "url": "",
                "filename": "",
                "title": "",
                "year": "",
                "source_type": "pdf",
                "page_count": "",
                "text": to_text(doc),
                "metadata": "",
            })

    # Some scraper versions keep PDF text separately
    raw_pdfs = data.get(
        "raw_text_pdfs",
        []
    )

    if isinstance(raw_pdfs, dict):

        raw_pdfs = [
            {
                "key": key,
                "data": value
            }
            for key, value in raw_pdfs.items()
        ]

    if isinstance(raw_pdfs, list):

        start_number = len(rows) + 1

        for i, pdf in enumerate(
            raw_pdfs,
            start=start_number
        ):

            if isinstance(pdf, dict):

                rows.append({
                    "institute_code": institute_code,
                    "institute_name": institute_name,
                    "document_number": i,
                    "url": pdf.get(
                        "url",
                        pdf.get(
                            "source_url",
                            ""
                        )
                    ),
                    "filename": pdf.get(
                        "filename",
                        ""
                    ),
                    "title": pdf.get(
                        "title",
                        ""
                    ),
                    "year": pdf.get(
                        "year",
                        ""
                    ),
                    "source_type": "pdf_text",
                    "page_count": pdf.get(
                        "page_count",
                        ""
                    ),
                    "text": to_text(
                        pdf.get(
                            "text",
                            pdf.get(
                                "content",
                                ""
                            )
                        )
                    ),
                    "metadata": to_json(pdf),
                })

            else:

                rows.append({
                    "institute_code": institute_code,
                    "institute_name": institute_name,
                    "document_number": i,
                    "url": "",
                    "filename": "",
                    "title": "",
                    "year": "",
                    "source_type": "pdf_text",
                    "page_count": "",
                    "text": to_text(pdf),
                    "metadata": "",
                })

    return rows


# ============================================================
# HISTORICAL CSV
# ============================================================

def make_historical_rows(data):

    rows = []

    institute_code = data.get(
        "institute_code",
        ""
    )

    institute_name = data.get(
        "institute_name",
        ""
    )

    historical = data.get(
        "historical",
        {}
    )

    flatten_evidence(
        historical,
        institute_code,
        institute_name,
        "historical",
        "historical",
        {},
        rows,
    )

    return rows


# ============================================================
# MAIN
# ============================================================

def main():

    json_files = get_json_files()

    if not json_files:

        print(
            "No college JSON files found in scraper_output/"
        )

        return

    print(
        f"Found {len(json_files)} college JSON file(s)"
    )

    colleges = []
    evidence = []
    placements = []
    recruiters = []
    admissions = []
    approvals = []
    accreditation = []
    rankings = []
    fees = []
    contacts = []
    pages = []
    documents = []
    historical = []

    # --------------------------------------------------------
    # PROCESS EACH COLLEGE
    # --------------------------------------------------------

    for json_path in json_files:

        data = load_json(json_path)

        if not data:
            continue

        code = data.get(
            "institute_code",
            ""
        )

        name = data.get(
            "institute_name",
            ""
        )

        print(
            f"Processing {code} - {name}"
        )

        # Copy JSON into json/
        shutil.copy2(
            json_path,
            JSON_DIR / json_path.name
        )

        # Overview
        colleges.append(
            make_college_row(data)
        )

        # ----------------------------------------------------
        # COMPLETE EVIDENCE
        # ----------------------------------------------------

        extracted = data.get(
            "extracted",
            {}
        )

        if isinstance(extracted, dict):

            for section, value in extracted.items():

                flatten_evidence(
                    value,
                    code,
                    name,
                    f"extracted.{section}",
                    section,
                    {},
                    evidence,
                )

        # Historical
        historical.extend(
            make_historical_rows(data)
        )

        # ----------------------------------------------------
        # SPECIALIZED DATA
        # ----------------------------------------------------

        placements.extend(
            make_placement_rows(data)
        )

        recruiters.extend(
            make_special_rows(
                data,
                "recruiter_mentions"
            )
        )

        admissions.extend(
            make_special_rows(
                data,
                "admission_mentions"
            )
        )

        approvals.extend(
            make_special_rows(
                data,
                "approval_mentions"
            )
        )

        rankings.extend(
            make_special_rows(
                data,
                "ranking_mentions"
            )
        )

        fees.extend(
            make_special_rows(
                data,
                "fees"
            )
        )

        # NAAC / NBA / NIRF together
        for field in (
            "naac",
            "nba",
            "nirf",
        ):

            accreditation.extend(
                make_special_rows(
                    data,
                    field
                )
            )

        contacts.extend(
            make_contact_rows(data)
        )

        pages.extend(
            make_page_rows(data)
        )

        documents.extend(
            make_document_rows(data)
        )

    # ========================================================
    # CSV FIELD DEFINITIONS
    # ========================================================

    overview_fields = [
        "institute_code",
        "institute_name",
        "official_url",
        "url_source",
        "scraped_at",
        "status",
        "established_year",
        "affiliation",
        "naac",
        "nba",
        "nirf",
        "fees",
        "placements",
        "recruiters",
        "admissions",
        "approvals",
        "rankings",
        "contact_mentions",
        "emails",
        "phones",
        "address",
        "historical",
        "documents",
        "quality",
        "pages_crawled",
        "pdf_count",
        "crawl_errors",
    ]

    evidence_fields = [
        "institute_code",
        "institute_name",
        "section",
        "field",
        "value",
        "kind",
        "year",
        "years_mentioned",
        "source_url",
        "source_type",
        "confidence",
        "context",
    ]

    special_fields = [
        "institute_code",
        "institute_name",
        "record_number",
        "value",
        "kind",
        "year",
        "years_mentioned",
        "source_url",
        "source_type",
        "confidence",
        "context",
    ]

    placement_fields = [
        "institute_code",
        "institute_name",
        "record_number",
        "company",
        "package_lpa",
        "value",
        "kind",
        "year",
        "years_mentioned",
        "source_url",
        "source_type",
        "confidence",
        "context",
    ]

    contact_fields = [
        "institute_code",
        "institute_name",
        "contact_type",
        "value",
    ]

    page_fields = [
        "institute_code",
        "institute_name",
        "page_number",
        "url",
        "title",
        "status",
        "text",
        "metadata",
    ]

    document_fields = [
        "institute_code",
        "institute_name",
        "document_number",
        "url",
        "filename",
        "title",
        "year",
        "source_type",
        "page_count",
        "text",
        "metadata",
    ]

    # ========================================================
    # WRITE CSV FILES
    # ========================================================

    write_csv(
        CSV_DIR / "colleges.csv",
        colleges,
        overview_fields,
    )

    write_csv(
        CSV_DIR / "college_evidence.csv",
        evidence,
        evidence_fields,
    )

    write_csv(
        CSV_DIR / "placements.csv",
        placements,
        placement_fields,
    )

    write_csv(
        CSV_DIR / "recruiters.csv",
        recruiters,
        special_fields,
    )

    write_csv(
        CSV_DIR / "admissions.csv",
        admissions,
        special_fields,
    )

    write_csv(
        CSV_DIR / "approvals.csv",
        approvals,
        special_fields,
    )

    write_csv(
        CSV_DIR / "accreditation.csv",
        accreditation,
        special_fields,
    )

    write_csv(
        CSV_DIR / "rankings.csv",
        rankings,
        special_fields,
    )

    write_csv(
        CSV_DIR / "fees.csv",
        fees,
        special_fields,
    )

    write_csv(
        CSV_DIR / "contacts.csv",
        contacts,
        contact_fields,
    )

    write_csv(
        CSV_DIR / "college_pages.csv",
        pages,
        page_fields,
    )

    write_csv(
        CSV_DIR / "college_documents.csv",
        documents,
        document_fields,
    )

    write_csv(
        CSV_DIR / "historical.csv",
        historical,
        evidence_fields,
    )

    # ========================================================
    # FINAL REPORT
    # ========================================================

    print()
    print("==============================================")
    print("FINAL CSV EXPORT")
    print("==============================================")

    print(
        f"Colleges       : {len(colleges)}"
    )

    print(
        f"Evidence       : {len(evidence)}"
    )

    print(
        f"Placements     : {len(placements)}"
    )

    print(
        f"Recruiters     : {len(recruiters)}"
    )

    print(
        f"Admissions     : {len(admissions)}"
    )

    print(
        f"Approvals      : {len(approvals)}"
    )

    print(
        f"Accreditation  : {len(accreditation)}"
    )

    print(
        f"Rankings       : {len(rankings)}"
    )

    print(
        f"Fees           : {len(fees)}"
    )

    print(
        f"Contacts       : {len(contacts)}"
    )

    print(
        f"Pages          : {len(pages)}"
    )

    print(
        f"Documents      : {len(documents)}"
    )

    print(
        f"Historical     : {len(historical)}"
    )

    print()
    print("CSV files created inside:")
    print(f"  {CSV_DIR}/")

    print()
    print("JSON files copied inside:")
    print(f"  {JSON_DIR}/")


if __name__ == "__main__":
    main()
