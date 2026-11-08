# -*- coding: utf-8 -*-
"""
Stream Recommendation Engine.
Calculates weighted compatibility scores across academic streams (PCM, PCB, Commerce, Arts/Humanities).
Adheres to Single Responsibility Principle (SRP).
"""

from typing import Dict, Any, List

class StreamRecommendationEngine:
    """Evaluates marks, self-reported interests, and aptitude test scores."""

    def recommend(
        self,
        marks: Dict[str, Any],
        interests: Dict[str, Any],
        aptitude_scores: Dict[str, Any]
    ) -> Dict[str, Any]:
        maths = float(marks.get("maths", 70))
        science = float(marks.get("science", 70))
        english = float(marks.get("english", 70))
        social = float(marks.get("social_science", 70))
        overall = float(marks.get("overall_percentage", (maths + science + english + social) / 4.0))

        interest_tags = set(interests.get("tags", []))
        ambitions_text = interests.get("text", "") or interests.get("ambitions", "")

        cat_scores = aptitude_scores.get("category_percentages") or {
            "logical": 75.0,
            "numerical": 75.0,
            "scientific": 75.0,
            "business": 60.0,
            "creative": 65.0,
            "communication": 70.0,
            "analytical": 70.0
        }

        # 1. Science (PCM) Score
        pcm_marks = (maths * 0.45) + (science * 0.40) + (overall * 0.15)
        pcm_apt = (cat_scores.get("numerical", 70) * 0.4) + (cat_scores.get("logical", 70) * 0.35) + (cat_scores.get("scientific", 70) * 0.25)
        pcm_boost = 0.0
        if "technology" in interest_tags or "engineering" in interest_tags or "maths_puzzles" in interest_tags:
            pcm_boost += 6.0
        if "software" in ambitions_text.lower() or "engineer" in ambitions_text.lower() or "tech" in ambitions_text.lower():
            pcm_boost += 4.0
        pcm_score = round(min(99.0, (pcm_marks * 0.5) + (pcm_apt * 0.4) + pcm_boost), 1)

        # 2. Science (PCB) Score
        pcb_marks = (science * 0.55) + (english * 0.25) + (overall * 0.20)
        pcb_apt = (cat_scores.get("scientific", 70) * 0.6) + (cat_scores.get("analytical", 70) * 0.4)
        pcb_boost = 0.0
        if "medicine" in interest_tags or "practical_labs" in interest_tags:
            pcb_boost += 6.0
        if "doctor" in ambitions_text.lower() or "medical" in ambitions_text.lower() or "bio" in ambitions_text.lower():
            pcb_boost += 4.0
        pcb_score = round(min(99.0, (pcb_marks * 0.5) + (pcb_apt * 0.4) + pcb_boost), 1)

        # 3. Commerce Score
        comm_marks = (maths * 0.35) + (english * 0.35) + (social * 0.30)
        comm_apt = (cat_scores.get("business", 70) * 0.5) + (cat_scores.get("numerical", 70) * 0.3) + (cat_scores.get("communication", 70) * 0.2)
        comm_boost = 0.0
        if "business" in interest_tags:
            comm_boost += 6.0
        if "finance" in ambitions_text.lower() or "ca" in ambitions_text.lower() or "business" in ambitions_text.lower():
            comm_boost += 4.0
        comm_score = round(min(99.0, (comm_marks * 0.5) + (comm_apt * 0.4) + comm_boost), 1)

        # 4. Arts & Humanities Score
        arts_marks = (social * 0.45) + (english * 0.40) + (overall * 0.15)
        arts_apt = (cat_scores.get("creative", 70) * 0.4) + (cat_scores.get("communication", 70) * 0.4) + (cat_scores.get("analytical", 70) * 0.2)
        arts_boost = 0.0
        if "design" in interest_tags or "law_civics" in interest_tags:
            arts_boost += 6.0
        if "upsc" in ambitions_text.lower() or "design" in ambitions_text.lower() or "law" in ambitions_text.lower():
            arts_boost += 4.0
        arts_score = round(min(99.0, (arts_marks * 0.5) + (arts_apt * 0.4) + arts_boost), 1)

        streams_data = [
            {
                "id": "science_pcm",
                "name": "Science (PCM)",
                "headline": "Physics, Chemistry, Mathematics — Ideal for Engineering & Computing",
                "score": pcm_score,
                "key_subjects": ["Physics", "Chemistry", "Mathematics", "Computer Science"],
                "career_pathways": ["B.Tech / B.E. (Computer, AI, Mechanical)", "Architecture (B.Arch)", "Data Science & AI", "Defense (NDA)"],
                "reasons": [
                    f"Strong quantitative foundation with {maths}% in Mathematics and {science}% in Science.",
                    f"High analytical aptitude score ({cat_scores.get('logical', 75)}% in Logical Reasoning)."
                ]
            },
            {
                "id": "science_pcb",
                "name": "Science (PCB)",
                "headline": "Physics, Chemistry, Biology — Healthcare, Medicine & Biotech",
                "score": pcb_score,
                "key_subjects": ["Physics", "Chemistry", "Biology", "Psychology"],
                "career_pathways": ["MBBS / BDS", "B.Pharm (Pharmacy)", "Biotechnology & Genetics", "Physiotherapy & Nursing"],
                "reasons": [
                    f"Scientific aptitude evaluated at {cat_scores.get('scientific', 75)}%.",
                    "Alignment with clinical, healthcare, and biological inquiry."
                ]
            },
            {
                "id": "commerce",
                "name": "Commerce & Finance",
                "headline": "Accountancy, Economics & Business — Corporate Leadership & Entrepreneurship",
                "score": comm_score,
                "key_subjects": ["Accountancy", "Economics", "Business Studies", "Applied Mathematics"],
                "career_pathways": ["Chartered Accountancy (CA)", "B.Com / BBA / MBA", "Investment Banking & FinTech", "Corporate Law"],
                "reasons": [
                    f"Business & commercial awareness aptitude of {cat_scores.get('business', 65)}%.",
                    "Strong quantitative and verbal reasoning balance."
                ]
            },
            {
                "id": "arts_humanities",
                "name": "Arts & Humanities",
                "headline": "Psychology, Political Science, Design & Media — Creative & Public Leadership",
                "score": arts_score,
                "key_subjects": ["Political Science", "Psychology", "History / Sociology", "Media & Communication"],
                "career_pathways": ["Civil Services (UPSC / MPSC)", "Product Design (NID / NIFT)", "Corporate Law & Public Policy", "Journalism & Media"],
                "reasons": [
                    f"Creative expression aptitude at {cat_scores.get('creative', 65)}%.",
                    "Excellent social science and linguistic expression."
                ]
            }
        ]

        streams_data.sort(key=lambda s: s["score"], reverse=True)
        recommended = streams_data[0]
        alternatives = streams_data[1:]

        strongest_cat = max(cat_scores, key=cat_scores.get) if cat_scores else "General Problem Solving"

        return {
            "success": True,
            "recommended_stream": recommended,
            "alternatives": alternatives,
            "all_streams": streams_data,
            "diagnostic_summary": {
                "top_aptitude_domain": strongest_cat.title(),
                "academic_baseline": overall,
                "engine_version": "Neev-StreamEngine-v2.0"
            }
        }
