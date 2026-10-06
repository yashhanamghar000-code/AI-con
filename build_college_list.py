#!/usr/bin/env python3
"""
Scan your hierarchical cutoff JSONs (any year folders produced by
extract_cutoffs_hierarchical.py) and build one deduplicated college list.

Run:
    python build_college_list.py --input ./out --out college_master.csv

--input should be the folder that CONTAINS the year folders, e.g.:
    out/
      2024-25/06315_sanjeevan_group_of_institutions.json ...
      2025-26/...
      2026-27/...

Output columns:
    institute_code, institute_name, status, home_university,
    years_seen, branch_count_latest_year, url (blank - fill in or let
    college_info_scraper.py search for it), notes

If a college's name differs slightly across years (e.g. a rename), both
names are kept in "name_variants" so nothing is silently merged away.
"""
import argparse, csv, json
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="folder containing year subfolders")
    ap.add_argument("--out", default="college_master.csv")
    args = ap.parse_args()

    colleges = defaultdict(lambda: {"names": set(), "statuses": set(), "home_unis": set(),
                                    "years": set(), "branches_by_year": {}})

    for year_dir in sorted(Path(args.input).iterdir()):
        if not year_dir.is_dir():
            continue
        for f in year_dir.glob("*.json"):
            if f.name == "_index.json":
                continue
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"skip {f}: {e}")
                continue
            code = d.get("institute_code")
            if not code:
                continue
            c = colleges[code]
            if d.get("institute_name"):
                c["names"].add(d["institute_name"])
            if d.get("status"):
                c["statuses"].add(d["status"])
            if d.get("home_university"):
                c["home_unis"].add(d["home_university"])
            c["years"].add(year_dir.name)
            c["branches_by_year"][year_dir.name] = len(d.get("branches", []))

    rows = []
    for code, c in sorted(colleges.items()):
        names = sorted(c["names"])
        latest_year = sorted(c["years"])[-1] if c["years"] else ""
        rows.append({
            "institute_code": code,
            "institute_name": names[0] if names else "",
            "name_variants": " | ".join(names[1:]) if len(names) > 1 else "",
            "status": " | ".join(sorted(c["statuses"])),
            "home_university": " | ".join(sorted(c["home_unis"])),
            "years_seen": " | ".join(sorted(c["years"])),
            "branch_count_latest_year": c["branches_by_year"].get(latest_year, ""),
            "url": "",
            "notes": "",
        })

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                           ["institute_code", "institute_name", "name_variants", "status",
                            "home_university", "years_seen", "branch_count_latest_year", "url", "notes"])
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} unique colleges written to {args.out}")
    multi_name = [r for r in rows if r["name_variants"]]
    if multi_name:
        print(f"{len(multi_name)} colleges have name variants across years - check name_variants column "
              "(could be a genuine rename, or two different colleges sharing a reused code - verify).")


if __name__ == "__main__":
    main()
