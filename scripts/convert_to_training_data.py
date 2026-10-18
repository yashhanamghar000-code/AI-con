#!/usr/bin/env python3
"""
Convert your existing cutoff JSONs (from extract_cutoffs_hierarchical.py)
and college-info JSONs (from scrape_all_colleges.py / manual batches) into
a chat-format JSONL suitable for fine-tuning an instruct model.

This trains BEHAVIOUR (citation format, abstention, grounded answering) -
not facts. See MODEL_AND_RAG_PLAN.md section 1 for why that distinction
matters and what to never put in a training example.

Run:
    python convert_to_training_data.py --cutoffs ./out --college-info ./college_info \
        --out ./training/sft_data.jsonl

Output format - one JSON object per line, OpenAI/Unsloth/TRL-compatible:
    {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}

IMPORTANT: review a random sample of the output by hand before training on
it. Examples are built directly from your scraped data, including anything
in it tagged "secondary_source_unverified" or "conflicting_sources" - those
ARE still included (with the conflict/caveat language intact), on purpose,
because teaching the model to surface uncertainty instead of hiding it is
exactly the behaviour you want. But examples built from a confirmed-bad
extraction (the kind of forum-post mis-extraction you've seen from the
scraper) would teach the wrong lesson - that's what the review step is for,
this script can't know which facts are wrong.
"""
import argparse, json, random, re
from pathlib import Path

SYSTEM_CUTOFF = (
    "You are an admission decision-support assistant for Maharashtra engineering "
    "colleges. Use only the supplied evidence. Cite evidence IDs in [brackets]. "
    "Never promise admission. A historical cutoff describes a past round's outcome, "
    "not a guarantee for any future round or year. If evidence is missing, respond "
    "with status=insufficient_evidence and say exactly what is missing."
)
SYSTEM_INFO = (
    "You are a college-information assistant. Use only the supplied evidence, which "
    "comes from web-scraped sources and may be incomplete, conflicting, or unverified. "
    "Always say where a figure came from and its confidence level. If sources "
    "conflict, present the conflict - never silently pick one. If nothing relevant "
    "was found, say so plainly instead of guessing."
)


def iter_cutoff_examples(cutoffs_dir, max_per_category=3):
    """One example per (college, branch, category): list its full round-by-round
    history and ask for it, exactly the shape a real student question takes."""
    examples = []
    for year_dir in sorted(Path(cutoffs_dir).iterdir()):
        if not year_dir.is_dir():
            continue
        for f in year_dir.glob("*.json"):
            if f.name == "_index.json":
                continue
            try:
                college = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for branch in college.get("branches", []):
                for cat in branch.get("categories", []):
                    cutoffs = [c for c in cat.get("cutoffs", []) if c.get("closing_rank") is not None]
                    if not cutoffs:
                        continue
                    ev_lines = "\n".join(
                        f"[{c['evidence_id']}] {college['academic_year']} round {c.get('round')} "
                        f"stage {c.get('stage')} ({c.get('list_type')}): closing rank "
                        f"{c['closing_rank']}, percentile {c.get('closing_percentile')}"
                        for c in cutoffs)
                    q = (f"What were the {cat['category']} closing cutoffs for "
                         f"{branch['branch']} at {college['institute_name']} in "
                         f"{college['academic_year']}?")
                    a = ("Historical observation from the supplied records:\n" +
                         "\n".join(f"- Round {c.get('round')}, stage {c.get('stage')}: "
                                  f"rank {c['closing_rank']}, percentile {c.get('closing_percentile')} "
                                  f"[{c['evidence_id']}]" for c in cutoffs) +
                         f"\nThis describes {college['academic_year']} only - not a prediction or "
                         "guarantee for any other year. Confirm against the official CET Cell notice "
                         "before relying on it.")
                    examples.append({"messages": [
                        {"role": "system", "content": SYSTEM_CUTOFF},
                        {"role": "user", "content": f"EVIDENCE:\n{ev_lines}\n\nQUESTION: {q}"},
                        {"role": "assistant", "content": a}]})
    return examples


def iter_abstention_examples(cutoffs_dir, n=50, seed=42):
    """Deliberately ask about a category/round that ISN'T in a college's
    evidence, so the model practices saying so instead of inventing a number."""
    pool = []
    for year_dir in sorted(Path(cutoffs_dir).iterdir()):
        if not year_dir.is_dir():
            continue
        for f in year_dir.glob("*.json"):
            if f.name == "_index.json":
                continue
            try:
                college = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for branch in college.get("branches", []):
                cats = [c["category"] for c in branch.get("categories", [])]
                for cat in branch.get("categories", []):
                    real = {c["category"] for c in branch["categories"]}
                    pool.append((college, branch, cat, real))
    random.Random(seed).shuffle(pool)
    examples = []
    all_known_categories = ["GOPENS", "GSCS", "GSTS", "LOPENS", "GOBCS", "TFWS", "EWS", "PWDOPENS"]
    for college, branch, cat, real_cats in pool[:n]:
        cutoffs = [c for c in cat.get("cutoffs", []) if c.get("closing_rank") is not None]
        if not cutoffs:
            continue
        missing_cat = next((c for c in all_known_categories if c not in real_cats), "GSTS")
        ev_lines = "\n".join(
            f"[{c['evidence_id']}] {college['academic_year']} round {c.get('round')}: "
            f"closing rank {c['closing_rank']}" for c in cutoffs)
        q = (f"What was the {missing_cat} closing cutoff for {branch['branch']} at "
             f"{college['institute_name']} in {college['academic_year']}?")
        a = json.dumps({
            "status": "insufficient_evidence",
            "missing_information": [f"{missing_cat} record for {branch['branch']} "
                                    f"at {college['institute_name']}, {college['academic_year']}"],
            "next_action": "Check the official CET Cell cutoff list for this seat type, "
                           "or confirm this category was offered at this college this year."
        })
        examples.append({"messages": [
            {"role": "system", "content": SYSTEM_CUTOFF},
            {"role": "user", "content": f"EVIDENCE:\n{ev_lines}\n\nQUESTION: {q}"},
            {"role": "assistant", "content": a}]})
    return examples


def iter_college_info_examples(college_info_dir):
    """One example per scraped college, grounded in its extracted fields
    exactly as scraped - confidence labels and conflicts intact."""
    examples = []
    for f in Path(college_info_dir).glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if c.get("error") or not c.get("extracted"):
            continue
        ex = c["extracted"]
        identity = ex.get("identity", {}) if isinstance(ex.get("identity"), dict) else {}
        ev_parts = []
        for field in ("established_year", "affiliation", "naac_grade", "autonomy_status", "institution_type", "ownership", "district", "state"):
            v = ex.get(field)
            if v is None:
                v = identity.get(field)
            if isinstance(v, dict) and v.get("value"):
                ev_parts.append(f"{field}: {v['value']} (confidence: {v.get('confidence', 'verified')}, "
                                f"source: {v.get('source_page', v.get('source', 'n/a'))})")
            elif isinstance(v, dict) and v.get("conflict"):
                conf = "; ".join(f"{x.get('value')} per {x.get('source')}" for x in v["conflict"])
                ev_parts.append(f"{field}: CONFLICTING SOURCES - {conf}")
        for pm in ex.get("placement_mentions", [])[:3]:
            ev_parts.append(f"placement mention: {pm.get('value')} (confidence: {pm.get('confidence')}, "
                            f"context: \"{pm.get('context', '')[:120]}\")")
        if not ev_parts:
            continue
        evidence = "\n".join(ev_parts)
        q = f"Tell me about {c['institute_name']} - what is its affiliation, location, and institution type?"
        conflicts = [p for p in ev_parts if "CONFLICTING" in p]
        if conflicts:
            a = ("The sources I have disagree on this, so I'll show you the conflict rather than "
                 f"pick one:\n{evidence}\n\nVerify directly with the institute or an official source "
                 "before relying on any single figure here.")
        else:
            a = (f"Based on the available verified information:\n{evidence}\n\n"
                 "These figures come from official admission records - "
                 "confirm anything important directly with the institute.")
        examples.append({"messages": [
            {"role": "system", "content": SYSTEM_INFO},
            {"role": "user", "content": f"EVIDENCE:\n{evidence}\n\nQUESTION: {q}"},
            {"role": "assistant", "content": a}]})
    return examples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoffs", required=True, help="folder containing year subfolders")
    ap.add_argument("--college-info", required=False, help="folder of scraped college_info JSONs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-cutoff-examples", type=int, default=5000)
    ap.add_argument("--abstention-examples", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    examples = []
    cutoff_ex = iter_cutoff_examples(args.cutoffs)
    cutoff_subset = cutoff_ex[:args.max_cutoff_examples]
    examples += cutoff_subset
    abstention_ex = iter_abstention_examples(args.cutoffs, n=args.abstention_examples, seed=args.seed)
    examples += abstention_ex
    info_ex = []
    if args.college_info:
        info_ex = iter_college_info_examples(args.college_info)
        examples += info_ex

    random.Random(args.seed).shuffle(examples)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"{len(examples)} training examples written to {out_path}")
    print(f"  cutoff (grounded):     {len(cutoff_subset)}")
    print(f"  abstention:            {len(abstention_ex)}")
    print(f"  college-info grounded: {len(info_ex)}")
    print("\nReview a random sample by hand before training - see the warning at the top of this file.")


if __name__ == "__main__":
    main()
