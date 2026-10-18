#!/usr/bin/env python3
"""
AI-CON 5-Level Model Testing Suite
----------------------------------
Sends 5 questions of increasing difficulty (Level 1 to Level 5) to:
1. AI-CON Model (`qwen2.5-aicon:latest`)
2. Reference Model (`qwen2.5:7b`)

Captures complete unedited outputs, timestamps, and latency for formal evaluation.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from ollama_client import call_ollama


QUESTIONS = [
    {
        "id": "Q1",
        "difficulty": "Level 1: Easy, Basic Counselling",
        "question": (
            "I scored 85 percentile in MHT-CET and want admission to a computer-related engineering "
            "branch in Maharashtra. Explain the main steps of the CAP admission process, how college "
            "preferences work, and which details you need before recommending colleges. Do not guarantee "
            "admission based on percentile alone."
        ),
    },
    {
        "id": "Q2",
        "difficulty": "Level 2: Moderate, Comparative Analysis",
        "question": (
            "Compare Computer Engineering, Information Technology, and Artificial Intelligence and Data "
            "Science for a student interested in software development and AI. Explain the differences in "
            "curriculum, typical career opportunities, and factors to consider when choosing between these "
            "branches. Clearly distinguish general industry trends from verified placement data."
        ),
    },
    {
        "id": "Q3",
        "difficulty": "Level 3: Hard, Cutoff Comparison",
        "question": (
            "I have an MHT-CET percentile of 92.40. I want to compare three engineering colleges for "
            "Computer Engineering using their official CAP cutoff data from the same admission year, "
            "round, admission type, category, and applicable seat type. Explain how to compare the "
            "cutoffs fairly, determine whether my percentile is above or below each cutoff, and identify "
            "the missing information required for a reliable admission estimate. Do not invent college "
            "names, cutoff values, or admission probabilities if verified data is unavailable."
        ),
    },
    {
        "id": "Q4",
        "difficulty": "Level 4: Very Hard, Conflicting Constraints",
        "question": (
            "A student has a 94.20 MHT-CET percentile and wants Computer Engineering or Information "
            "Technology in Pune. The student belongs to a reserved category but has not confirmed "
            "eligibility documents, domicile status, or the applicable seat type. The student prefers "
            "colleges with lower fees, good placement opportunities, and a short commute. Develop a "
            "counselling strategy that balances these competing priorities. Explain how category eligibility, "
            "official cutoff data, fees, placement evidence, and commute should be verified. Do not promise "
            "admission or treat unverified category eligibility as established."
        ),
    },
    {
        "id": "Q5",
        "difficulty": "Level 5: Extremely Hard, Multi-Constraint Counselling",
        "question": (
            "Design a transparent, evidence-based CAP counselling recommendation for this hypothetical student:\n\n"
            "- MHT-CET percentile: 96.35\n"
            "- Preferred location: Pune and nearby areas\n"
            "- Preferred branches: Computer Engineering, Information Technology, AI and Data Science\n"
            "- Budget: Maximum ₹1.5 lakh per year in total educational expenses\n"
            "- Priority order: Branch preference, affordability, then placement opportunities\n"
            "- Category, domicile eligibility, gender-related seat eligibility, and applicable seat type: Not provided\n"
            "- Official cutoff records: May contain multiple admission years, CAP rounds, categories, and seat types\n\n"
            "Explain your complete decision process. Identify all missing information. Describe how you would "
            "validate the cutoff records, remove invalid comparisons, rank suitable options, account for "
            "uncertainty, and handle cases where no option can be responsibly recommended from the available "
            "evidence. Distinguish eligibility, likelihood, and guarantee of admission. Never fabricate cutoff "
            "figures, fees, placement statistics, or official rules. If data is missing, specify exactly what is "
            "needed before producing a final college shortlist."
        ),
    },
]


def run_test():
    print("=" * 80)
    print("STARTING 5-LEVEL MODEL EVALUATION TEST: AI-CON vs REFERENCE (Qwen 2.5 7B)")
    print("=" * 80)

    results: List[Dict[str, Any]] = []

    aicon_system = (
        "You are an admission decision-support assistant for Maharashtra engineering colleges (AI-CON). "
        "Follow strict anti-hallucination rules: Never promise admission. If specific evidence or inputs "
        "are missing, identify the missing information and abstain or state insufficient evidence. Never "
        "invent numerical cutoffs, college fees, or placement figures."
    )
    ref_system = (
        "You are an expert educational and admissions counselling AI assistant. Provide thorough, "
        "objective, accurate, and structured advice."
    )

    for item in QUESTIONS:
        qid = item["id"]
        diff = item["difficulty"]
        q_text = item["question"]
        print(f"\n--- Running {qid} ({diff}) ---")

        # 1. AI-CON Model Call
        t0 = time.time()
        print(f"Calling AI-CON model (qwen2.5-aicon:latest)...")
        try:
            aicon_out = call_ollama(
                system=aicon_system,
                user=q_text,
                model="qwen2.5-aicon:latest",
                timeout=120.0,
            )
        except Exception as e:
            aicon_out = f"ERROR: {e}"
        aicon_lat = round(time.time() - t0, 2)
        print(f"  AI-CON answered in {aicon_lat}s")

        # 2. Reference Model Call
        t1 = time.time()
        print(f"Calling Reference model (qwen2.5:7b)...")
        try:
            ref_out = call_ollama(
                system=ref_system,
                user=q_text,
                model="qwen2.5:7b",
                timeout=120.0,
            )
        except Exception as e:
            ref_out = f"ERROR: {e}"
        ref_lat = round(time.time() - t1, 2)
        print(f"  Reference answered in {ref_lat}s")

        results.append({
            "id": qid,
            "difficulty": diff,
            "question": q_text,
            "aicon": {
                "model": "qwen2.5-aicon:latest",
                "answer": aicon_out,
                "latency_sec": aicon_lat,
            },
            "reference": {
                "model": "qwen2.5:7b",
                "answer": ref_out,
                "latency_sec": ref_lat,
            },
        })

    out_file = Path("model_artifacts/five_level_test_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nAll 5 levels tested! Saved full raw outputs to: {out_file}")


if __name__ == "__main__":
    run_test()
