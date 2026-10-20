import csv
import re
import requests
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

MASTER = "V4_daataa/college_master.csv"
DIRECTORY = "V4_daataa/sppu_college_directory.csv"
OUTPUT = "V4_daataa/college_master_enriched.csv"
REPORT = "V4_daataa/sppu_match_report.csv"

SPPU_URL = "https://bcud.unipune.ac.in/utilities/college_search/All_Colleges.aspx"


def clean(text):
    text = str(text or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def similarity(a, b):
    """
    Robust college-name matching.

    The SPPU directory often contains:
      SOCIETY NAME + COLLEGE NAME + ADDR: ...

    while our CET dataset usually contains only:
      COLLEGE NAME, CITY

    Therefore we use token containment instead of relying mainly
    on whole-string similarity.
    """

    def normalize_name(text):
        text = str(text or "").lower()

        # Remove address and trailing Details text
        text = re.sub(
            r"\baddr\s*:.*$",
            " ",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"\bdetails\b.*$",
            " ",
            text,
            flags=re.IGNORECASE
        )

        text = text.replace("&", " and ")

        text = re.sub(
            r"[^a-z0-9]+",
            " ",
            text
        )

        return " ".join(text.split())

    stopwords = {
        "the",
        "of",
        "and",
        "college",
        "engineering",
        "engineer",
        "technology",
        "technical",
        "institute",
        "institutes",
        "educational",
        "education",
        "society",
        "trust",
        "foundation",
        "mandal",
        "mandals",
        "charitable",
        "university",
        "autonomous",
        "private",
        "public",
        "research",
        "center",
        "centre",
        "school",
        "management",
        "polytechnic",
        "for",
        "women",
        "sanstha",
        "shikshan",
        "shiksh",
        "prasar",
        "prasarak",
        "seva",
        "vikas",
        "gramin",
        "technical",
        "campus",
    }

    def tokens(text):
        return {
            token
            for token in normalize_name(text).split()
            if token not in stopwords
            and len(token) >= 2
        }

    na = normalize_name(a)
    nb = normalize_name(b)

    if not na or not nb:
        return 0.0

    ta = tokens(a)
    tb = tokens(b)

    if not ta or not tb:
        return 0.0

    intersection = ta & tb

    containment = len(intersection) / min(
        len(ta),
        len(tb)
    )

    union_score = len(intersection) / len(
        ta | tb
    )

    sequence_score = SequenceMatcher(
        None,
        " ".join(sorted(ta)),
        " ".join(sorted(tb))
    ).ratio()

    # Strong reward when every meaningful token
    # from one name appears in the other.
    if containment >= 0.90:
        return 0.98

    score = (
        0.65 * containment
        + 0.20 * sequence_score
        + 0.15 * union_score
    )

    return score

def normalize_url(url):
    url = str(url or "").strip()

    if not url:
        return ""

    if url.lower() in {"na", "n/a", "-", "--"}:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url


def download_sppu():

    print("Downloading official SPPU directory...")

    r = requests.get(
        SPPU_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )

    r.raise_for_status()

    print("STATUS:", r.status_code)
    print("HTML SIZE:", len(r.text))

    return r.text


def parse_sppu(html):

    soup = BeautifulSoup(html, "html.parser")

    target_header = "Puncode College College_Type Telephone EMail Running_Faculties District Taluka Establishment_Year Website_link"

    records = []

    # Look through every table.
    for table_no, table in enumerate(
        soup.find_all("table"),
        start=1
    ):

        text = table.get_text(
            " ",
            strip=True
        )

        if (
            "Puncode" not in text
            or "Website_link" not in text
            or "Establishment_Year" not in text
        ):
            continue

        print(
            f"Found possible SPPU table: {table_no}"
        )

        # IMPORTANT:
        # Use ONLY direct children of each TR.
        for tr in table.find_all(
            "tr",
            recursive=True
        ):

            cells = tr.find_all(
                ["td", "th"],
                recursive=False
            )

            values = [
                c.get_text(
                    " ",
                    strip=True
                )
                for c in cells
            ]

            # Normal case: 10 columns
            if len(values) >= 10:

                record = {
                    "Puncode": values[0],
                    "College": values[1],
                    "College_Type": values[2],
                    "Telephone": values[3],
                    "EMail": values[4],
                    "Running_Faculties": values[5],
                    "District": values[6],
                    "Taluka": values[7],
                    "Establishment_Year": values[8],
                    "Website_link": values[9],
                }

                if record["Puncode"] != "Puncode":
                    records.append(record)

                continue

            # Some rows are rendered as one text cell.
            row_text = tr.get_text(
                " ",
                strip=True
            )

            if not row_text:
                continue

            if row_text.startswith("Puncode"):
                continue

            # Extract website
            url_match = re.search(
                r"(https?://[^\s|]+|www\.[^\s|]+)",
                row_text,
                re.IGNORECASE
            )

            website = (
                url_match.group(1)
                if url_match
                else ""
            )

            # Remove final Details marker
            row_text = re.sub(
                r"\s+Details\s*$",
                "",
                row_text,
                flags=re.IGNORECASE
            )

            # Try pipe-based format
            parts = [
                x.strip()
                for x in row_text.split("|")
            ]

            if len(parts) >= 9:

                # First fields
                record = {
                    "Puncode": parts[0],
                    "College": parts[1],
                    "College_Type": parts[2],
                    "Telephone": parts[3],
                    "EMail": parts[4],
                    "Running_Faculties": parts[5],
                    "District": parts[6],
                    "Taluka": parts[7],
                    "Establishment_Year": parts[8],
                    "Website_link": website,
                }

                records.append(record)

    # Keep only engineering-related records.
    # SPPU directory contains Law, Pharmacy, Education,
    # Architecture, Management, etc.
    records = [
        r for r in records
        if "engineering" in (
            r.get("Running_Faculties", "") or ""
        ).lower()
        or "engineering" in (
            r.get("College", "") or ""
        ).lower()
    ]

    print(
        "Engineering records after filter:",
        len(records)
    )

    # Remove duplicates
    unique = {}

    for r in records:

        key = (
            r.get("Puncode", "").strip(),
            r.get("College", "").strip()
        )

        if key not in unique:
            unique[key] = r

    records = list(unique.values())

    print(
        "Total parsed records:",
        len(records)
    )

    return records


def save_directory(records):

    fields = [
        "Puncode",
        "College",
        "College_Type",
        "Telephone",
        "EMail",
        "Running_Faculties",
        "District",
        "Taluka",
        "Establishment_Year",
        "Website_link",
    ]

    with open(
        DIRECTORY,
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        writer.writeheader()
        writer.writerows(records)

    print(
        "Saved:",
        DIRECTORY
    )


def main():

    html = download_sppu()

    sppu = parse_sppu(html)

    if not sppu:
        raise RuntimeError(
            "No SPPU records were parsed."
        )

    save_directory(sppu)

    # -------------------------------------------------
    # Read our 703 college master
    # -------------------------------------------------

    with open(
        MASTER,
        "r",
        encoding="utf-8",
        newline=""
    ) as f:

        master = list(
            csv.DictReader(f)
        )

    new_fields = list(
        master[0].keys()
    ) + [
        "directory_website",
        "directory_phone",
        "directory_email",
        "directory_establishment_year",
        "directory_district",
        "directory_taluka",
        "directory_college_type",
        "directory_source",
        "directory_match_score",
    ]

    new_fields = list(
        dict.fromkeys(new_fields)
    )

    report = []

    matched = 0

    for row in master:

        university = clean(
            row.get(
                "home_university",
                ""
            )
        )

        # Only SPPU colleges
        if "savitribai phule pune university" not in university:
            continue

        name = row.get(
            "institute_name",
            ""
        )

        best = None
        best_score = 0.0

        for candidate in sppu:

            score = similarity(
                name,
                candidate.get(
                    "College",
                    ""
                )
            )

            if score > best_score:
                best_score = score
                best = candidate

        # Initialize
        row["directory_website"] = ""
        row["directory_phone"] = ""
        row["directory_email"] = ""
        row["directory_establishment_year"] = ""
        row["directory_district"] = ""
        row["directory_taluka"] = ""
        row["directory_college_type"] = ""
        row["directory_source"] = ""
        row["directory_match_score"] = ""

        confidence = "none"

        if best:

            if best_score >= 0.75:
                confidence = "high"

            elif best_score >= 0.60:
                confidence = "medium"

            else:
                confidence = "low"

            # Only accept reasonable matches
            if best_score >= 0.60:

                matched += 1

                row["directory_website"] = normalize_url(
                    best.get(
                        "Website_link",
                        ""
                    )
                )

                row["directory_phone"] = best.get(
                    "Telephone",
                    ""
                )

                row["directory_email"] = best.get(
                    "EMail",
                    ""
                )

                row["directory_establishment_year"] = best.get(
                    "Establishment_Year",
                    ""
                )

                row["directory_district"] = best.get(
                    "District",
                    ""
                )

                row["directory_taluka"] = best.get(
                    "Taluka",
                    ""
                )

                row["directory_college_type"] = best.get(
                    "College_Type",
                    ""
                )

                row["directory_source"] = (
                    "official_sppu_directory"
                )

                row["directory_match_score"] = (
                    f"{best_score:.3f}"
                )

        report.append({
            "institute_code": row.get(
                "institute_code",
                ""
            ),
            "institute_name": name,
            "matched_college": (
                best.get("College", "")
                if best else ""
            ),
            "website": (
                normalize_url(
                    best.get(
                        "Website_link",
                        ""
                    )
                )
                if best and best_score >= 0.60
                else ""
            ),
            "score": f"{best_score:.3f}",
            "confidence": confidence,
        })

    # Save enriched 703-college master
    with open(
        OUTPUT,
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=new_fields
        )

        writer.writeheader()
        writer.writerows(master)

    # Save report
    report_fields = [
        "institute_code",
        "institute_name",
        "matched_college",
        "website",
        "score",
        "confidence",
    ]

    with open(
        REPORT,
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=report_fields
        )

        writer.writeheader()
        writer.writerows(report)

    print()
    print("===================================")
    print("SPPU MAPPING FINISHED")
    print("===================================")
    print("SPPU directory records :", len(sppu))
    print("SPPU colleges matched  :", matched)
    print()
    print("Created:")
    print(DIRECTORY)
    print(OUTPUT)
    print(REPORT)


if __name__ == "__main__":
    main()
