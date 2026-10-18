"""
CutoffAgent: exact structured lookup over hierarchical cutoff JSONs.
Deliberately contains NO embeddings, NO fuzzy matching of numbers, and NO
LLM call - a cutoff question has exactly one correct answer per
college + branch + category + round, and this agent's whole job is to never
return anything except that exact answer or an explicit "not found".

Expected Hierarchical Schema (for future phases):
-------------------------------------------------
Directory structure:
  <cutoffs_dir>/
    <academic_year>/          (e.g., "2024-25", "2025-26")
      <institute_code>.json   (e.g., "01002.json")

Schema of each <institute_code>.json:
{
  "institute_code": "01002",
  "institute_name": "Government College of Engineering, Amravati",
  "academic_year": "2025-26",
  "branches": [
    {
      "branch": "Computer Engineering",
      "categories": [
        {
          "category": "GOPENS",
          "category_meaning": "General Open State-level",
          "cutoffs": [
            {
              "round": 1,
              "stage": "1",
              "list_type": "CAP",
              "closing_rank": 1234,
              "closing_percentile": 98.15,
              "evidence_id": "EV-01002-COMP-GOPENS-R1"
            }
          ]
        }
      ]
    }
  ]
}
"""
from __future__ import annotations

import argparse
import json
import re
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
    # 1. Normalize EV-1002-... to EV-01002-...
    norm = re.sub(r"^EV-(\d{4})-", r"EV-0\1-", norm)
    # 2. Normalize colon format institute code: 2020-21:1002:... to 2020-21:01002:...
    norm = re.sub(r"^(\d{4}-\d{2}):(\d{4}):", r"\1:0\2:", norm)
    # 3. Normalize 9-digit course code in colon format: ...:100224210:... to ...:0100224210:...
    norm = re.sub(r"^(\d{4}-\d{2}:\d{5}):(\d{9}):", r"\1:0\2:", norm)
    norm = re.sub(r"^(\d{4}-\d{2}):(\d{4}):(\d{9}):", r"\1:0\2:0\3:", norm)
    source_id = raw_s if norm != raw_s else None
    return norm, source_id


class CutoffAgent:
    def __init__(self, cutoffs_dir: Union[str, Path]):
        self.cutoffs_dir = Path(cutoffs_dir)
        self._by_code: Dict[str, Dict[str, Dict[str, Any]]] = {}  # institute_code -> {year: college_dict}
        if not self.cutoffs_dir.is_dir():
            raise FileNotFoundError(f"Cutoffs directory not found: {self.cutoffs_dir}")
        self._load_all()

    def _load_all(self) -> None:
        """Scan year directories and index cutoff files by institute code."""
        for year_dir in sorted(self.cutoffs_dir.iterdir()):
            if not year_dir.is_dir() or not re.match(r"^\d{4}-\d{2}$", year_dir.name):
                continue
            for f in year_dir.glob("*.json"):
                if f.name.startswith((".", "_")) or f.name in ("manifest.json", "schema.json"):
                    continue
                try:
                    college = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                code = college.get("institute_code")
                if not code:
                    continue
                ay = str(college.get("academic_year") or year_dir.name).strip()
                code_str = str(code).strip()
                self._by_code.setdefault(code_str, {})[ay] = college
                # Also index with 5-digit zero-padding if applicable
                if len(code_str) == 4 and code_str.isdigit():
                    self._by_code.setdefault(code_str.zfill(5), {})[ay] = college

    def years_available(self, institute_code: Union[str, int]) -> List[str]:
        """Return sorted list of academic years available for an institute."""
        code_str = str(institute_code).strip()
        years = self._by_code.get(code_str, {})
        if not years and len(code_str) == 4 and code_str.isdigit():
            years = self._by_code.get(code_str.zfill(5), {})
        return sorted(years.keys())

    def get_cutoffs(
        self,
        institute_code: Union[str, int],
        year: Optional[str] = None,
        branch_query: Optional[str] = None,
        category: Optional[str] = None,
        round_no: Optional[int] = None,
        list_type: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Returns matching cutoff records with full evidence, or empty list.

        Never guesses, interpolates, or predicts future cutoffs.
        """
        code_str = str(institute_code).strip()
        years = [year] if year else self.years_available(code_str)
        results: List[Dict[str, Any]] = []

        college_year_map = self._by_code.get(code_str)
        if not college_year_map and len(code_str) == 4 and code_str.isdigit():
            college_year_map = self._by_code.get(code_str.zfill(5), {})

        if not college_year_map:
            return []

        for y in years:
            college = college_year_map.get(y)
            if not college:
                continue
            for branch in college.get("branches", []):
                branch_name = branch.get("branch") or ""
                if branch_query and branch_query.lower() not in branch_name.lower():
                    continue
                for cat in branch.get("categories", []):
                    cat_name = cat.get("category", "")
                    if category and cat_name.upper() != category.upper():
                        continue
                    for cutoff in cat.get("cutoffs", []):
                        if round_no and cutoff.get("round") != round_no:
                            continue
                        if cutoff.get("closing_rank") is None:
                            continue
                        if list_type and canonical_list_type(cutoff.get("list_type")) != canonical_list_type(list_type):
                            continue
                        if stage and str(cutoff.get("stage", "1")) != str(stage):
                            continue
                        c_entry = dict(cutoff)
                        raw_ev = c_entry.get("evidence_id")
                        if raw_ev:
                            norm_ev, src_ev = canonicalize_evidence_id(raw_ev)
                            if norm_ev:
                                c_entry["evidence_id"] = norm_ev
                            if src_ev and not c_entry.get("source_evidence_id"):
                                c_entry["source_evidence_id"] = src_ev
                        results.append({
                            "academic_year": y,
                            "institute_code": code_str.zfill(5) if len(code_str) == 4 and code_str.isdigit() else code_str,
                            "institute_name": college.get("institute_name"),
                            "branch": branch_name,
                            "category": cat_name,
                            "category_meaning": cat.get("category_meaning"),
                            **c_entry,
                        })
        return results

    def list_branches(self, institute_code: Union[str, int], year: Optional[str] = None) -> List[str]:
        """Return sorted unique list of branches offered at an institute."""
        code_str = str(institute_code).strip()
        years = [year] if year else self.years_available(code_str)
        branches: Set[str] = set()

        college_year_map = self._by_code.get(code_str)
        if not college_year_map and len(code_str) == 4 and code_str.isdigit():
            college_year_map = self._by_code.get(code_str.zfill(5), {})

        if not college_year_map:
            return []

        for y in years:
            college = college_year_map.get(y)
            if college:
                branches.update(b.get("branch") for b in college.get("branches", []) if b.get("branch"))
        return sorted(branches)

    def as_evidence_text(self, results: List[Dict[str, Any]]) -> str:
        """Format get_cutoffs() results as evidence text with citations."""
        if not results:
            return "No matching cutoff records found."
        lines: List[str] = []
        for r in results:
            ev_id = r.get("evidence_id") or f"EV-{r['institute_code']}-{r.get('round')}"
            meaning = f" ({r['category_meaning']})" if r.get("category_meaning") else ""
            src_str = ""
            if r.get("source_file"):
                src_str = f" (source: {r['source_file']}"
                if r.get("page") is not None:
                    src_str += f", page {r['page']}"
                src_str += ")"
            lines.append(
                f"[{ev_id}] {r['academic_year']} {r['institute_name']} - "
                f"{r['branch']} - {r['category']}{meaning}: "
                f"round {r.get('round')} stage {r.get('stage')}, closing rank {r['closing_rank']}, "
                f"percentile {r.get('closing_percentile')}, list type {r.get('list_type')}{src_str}"
            )
        return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Quick manual test of CutoffAgent")
    ap.add_argument("--cutoffs", required=True)
    ap.add_argument("--institute-code", required=True)
    ap.add_argument("--branch", default=None)
    ap.add_argument("--category", default=None)
    args = ap.parse_args()

    agent = CutoffAgent(args.cutoffs)
    print("years available:", agent.years_available(args.institute_code))
    print("branches:", agent.list_branches(args.institute_code))
    results = agent.get_cutoffs(args.institute_code, branch_query=args.branch, category=args.category)
    print(agent.as_evidence_text(results))
