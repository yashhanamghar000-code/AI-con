#!/usr/bin/env python3
"""
AI-CON Model Evaluation Report Generator
=========================================
Generates the comprehensive ~20-page technical evaluation report in both
PDF format (via ReportLab) and Markdown format, analyzing the 5-level
MHT-CET counselling benchmark comparing AI-CON vs. Reference Model (Qwen 2.5 7B).

Artifacts Produced:
  - AI_CON_Model_Evaluation_Report.pdf
  - AI_CON_Model_Evaluation_Report.md
  - README.md
  - AI_CON_Evaluation_Report.zip
"""
from __future__ import annotations

import html
import json
import os
import sys
import textwrap
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# ReportLab Imports
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for dynamic 'Page X of Y' numbering and running headers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            if self._pageNumber > 1:
                self.saveState()
                self.setFont("Helvetica", 8)
                self.setFillColor(colors.HexColor("#64748B"))

                # Running Header
                self.drawString(
                    40, 808, "AI-CON vs Qwen 2.5 7B: Technical Evaluation Report (MHT-CET Counselling)"
                )
                self.setStrokeColor(colors.HexColor("#CBD5E1"))
                self.setLineWidth(0.5)
                self.line(40, 802, 555, 802)

                # Running Footer
                self.line(40, 45, 555, 45)
                self.drawString(
                    40, 32, "Confidential - Admissions Decision Support Evaluation"
                )
                self.drawRightString(
                    555, 32, f"Page {self._pageNumber} of {num_pages}"
                )
                self.restoreState()
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def make_code_flowables(text: str, style: ParagraphStyle, max_width: int = 92) -> List[Preformatted]:
    """Format, word-wrap, and split verbatim output into paragraph-level Preformatted flowables."""
    flowables = []
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text] if text.strip() else []
    for p in paragraphs:
        wrapped_lines = []
        for line in p.splitlines():
            if len(line) <= max_width:
                wrapped_lines.append(line)
            else:
                wrapped_lines.extend(textwrap.wrap(line, width=max_width))
        wrapped_text = "\n".join(wrapped_lines)
        flowables.append(Preformatted(html.escape(wrapped_text), style))
    return flowables


def load_test_results(json_path: Path) -> List[Dict[str, Any]]:
    """Load benchmark test results JSON."""
    if not json_path.is_file():
        raise FileNotFoundError(f"Test results JSON missing at: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_markdown_report(data: List[Dict[str, Any]], md_path: Path):
    """Write the complete Markdown version of the evaluation report."""
    md_text = f"""# AI-CON Model Technical Evaluation Report
## Comparative Assessment of AI-CON vs. Qwen 2.5 7B on MHT-CET Engineering Admissions Counselling

**Document Version:** 1.0.0  
**Evaluation Date:** October 2026  
**Status:** Completed & Audited  
**Overall Scores:**  
- **AI-CON (`qwen2.5-aicon:latest`):** 29.5 / 50 (59.0%)  
- **Reference Model (`qwen2.5:7b`):** 33.0 / 50 (66.0%)  

---

## 1. Executive Summary

This technical report documents the empirical evaluation of the **AI-CON decision-support model** against a reference model (**Qwen 2.5 7B**) across five progressively challenging admissions counselling tasks (Level 1 Easy to Level 5 Extremely Hard). 

The primary domain is the **Maharashtra Centralized Admission Process (CAP)** for undergraduate engineering (B.E./B.Tech) admissions, governed by the State Common Entrance Test Cell, Maharashtra.

### Core Findings
1. **Mathematical Reasoning Vulnerability in AI-CON**:
   In Level 3 (Hard), AI-CON committed a critical inequality inversion error by evaluating `92.40 > 95` as `True` and advising the student that they were eligible for a college with a 95.00 cutoff. This failure demonstrates that generative language models cannot be trusted with raw numerical cutoff comparisons.
2. **Geographical Hallucination in Reference Model**:
   In Level 4 (Very Hard), the reference model recommended *Shri Ramdeobaba College of Engineering and Management (SRCEM)* for a student requesting a short commute within Pune. SRCEM is located in **Nagpur**, over 700 km from Pune.
3. **Regulatory Authority Hallucinations**:
   AI-CON fabricated non-existent bodies (*"Maharashtra University"* and *"Maharashtra University of Engineering and Technology - MSET"*), while the reference model incorrectly claimed **MSBTE** (the polytechnic diploma board) conducts degree engineering admissions.
4. **Architectural Imperative**:
   Both models failed negative constraints by inventing mock college cards and cutoffs when information was missing. This confirms the necessity of AI-CON's **4-tier hybrid architecture**, where cutoff lookups, eligibility checks, and rank regressions are strictly handled by deterministic engines (`CutoffAgent`), and generative LLMs are restricted to evidence explanation.

---

## 2. Project Overview & Testing Objectives

The AI-CON project addresses the complexity of Maharashtra engineering CAP admissions:
- **181,137 historical cutoff records** across 6 academic years (2020-21 through 2025-26).
- **1,041 verified college profiles** across Maharashtra.
- **Dynamic seat allocations** based on Home University (HU), Other than Home University (OHU), State Level (SL), and reservation quotas (GOPENS, LOPENS, TFWS, EWS, OBC, SC, ST).

### Testing Objectives
1. Measure factual correctness regarding official Maharashtra CET Cell regulations.
2. Evaluate mathematical and threshold reasoning under exact percentile constraints.
3. Test anti-hallucination and abstention behaviors when crucial student information is omitted.
4. Assess handling of competing real-world constraints (fees, location, commute, placements).

---

## 3. Models Evaluated & Testing Methodology

| Parameter | AI-CON Model (`qwen2.5-aicon:latest`) | Reference Model (`qwen2.5:7b`) |
|:---|:---|:---|
| **Base Architecture** | Qwen2 (36 layers, 2048 hidden dimension) | Qwen2 (28 layers, 3584 hidden dimension) |
| **Quantization** | GGUF Q5_K_M (5-bit K-quant medium) | 16-bit / 4-bit standard Ollama serving |
| **System Prompt** | Strictly grounded admissions decision-support | General educational counselling assistant |
| **Serving Framework** | Local Ollama Daemon | Local Ollama Daemon |
| **Temperature** | 0.0 (Deterministic) | 0.0 (Deterministic) |

### Scoring Rubric (Out of 10 Points per Question)
- **Factual Correctness (0–3):** Compliance with official CET Cell rules and verified cutoff numbers.
- **Reasoning and Comparison (0–2):** Logical validity, inequality evaluation, and trade-off balancing.
- **Completeness (0–2):** Coverage of necessary procedural steps and quota dimensions.
- **Handling of Uncertainty (0–2):** Prompting for missing details, abstaining without evidence.
- **Clear Explanation (0–1):** Pedagogical clarity and readability.

---

## 4. Five-Question Score Comparison Table

| Question | Difficulty | AI-CON Score (/10) | Reference Score (/10) | Main Factual Errors | Missing Info Handling |
|:---|:---|:---:|:---:|:---|:---|
| **Q1: Basic Counselling** | Level 1: Easy | **4.5** | **6.0** | AI-CON: "Maharashtra University" authority, 5-preference limit, ₹2000 fee.<br>Ref: MSBTE conducts CAP, 15-college limit, post-allotment verification. | AI-CON: Prompted for score, category, college list.<br>Ref: Requested rank, category, HSC marks. |
| **Q2: Comparative Analysis** | Level 2: Moderate | **7.5** | **8.0** | AI-CON: Minor split of AI and DS.<br>Ref: None significant. | Both separated macro trends from institution placement data. |
| **Q3: Cutoff Comparison** | Level 3: Hard | **5.0** | **7.0** | AI-CON: Severe mathematical error (`92.40 > 95`); invented mock numbers.<br>Ref: Invented mock numbers instead of strict abstention. | Both identified missing category, round, and quota. |
| **Q4: Conflicting Constraints** | Level 4: Very Hard | **6.5** | **5.5** | AI-CON: Fabricated "MSET" university.<br>Ref: Major geographical hallucination (Ramdeobaba in Pune). | AI-CON: Refused to assume reserved status.<br>Ref: Assigned unverified OBC/SC/ST tags. |
| **Q5: Multi-Constraint** | Level 5: Extremely Hard | **6.0** | **6.5** | Both models violated negative constraint by generating mock College A/B/C cards. | AI-CON: Excellent eligibility vs guarantee separation.<br>Ref: Detailed audit process. |
| **TOTAL** | **All 5 Levels** | **29.5 / 50 (59%)** | **33.0 / 50 (66%)** | *(See detailed breakdowns)* | *(Both struggle with zero-shot abstention)* |

---

## 5. Detailed Question-by-Question Analysis

"""
    for item in data:
        qid = item["id"]
        diff = item["difficulty"]
        q_text = item["question"]
        a_ans = item["aicon"]["answer"]
        r_ans = item["reference"]["answer"]
        a_lat = item["aicon"]["latency_sec"]
        r_lat = item["reference"]["latency_sec"]

        md_text += f"""### {qid}: {diff}

#### Exact Question Asked
> {q_text}

#### Complete AI-CON Answer (Verbatim, Latency: {a_lat}s)
```text
{a_ans}
```

#### Complete Reference Model Answer (Verbatim, Latency: {r_lat}s)
```text
{r_ans}
```

---
"""

    md_text += """
## 6. Model Strengths and Weaknesses Comparison

| Model | Core Strengths | Observed Vulnerabilities |
|:---|:---|:---|
| **AI-CON**<br/>(`qwen2.5-aicon:latest`)<br/>*Overall Score: 29.5/50 (59%)* | • **Conceptual Rigor**: Clearly separates statutory eligibility from statistical likelihood and admission guarantees (Q5 Step 6).<br/>• **Document Verification**: Strictly requires Caste Validity Certificate and Non-Creamy Layer (NCL) before evaluating category quotas (Q4).<br/>• **Low Latency & Footprint**: 20.44s average CPU latency (1.85x faster than reference); runs comfortably in ~2.5 GB RAM on consumer hardware. | • **Arithmetic Inversion**: Falsely evaluated `92.40 > 95` as eligible (Q3).<br/>• **Regulatory Hallucination**: Fabricated non-existent authorities "Maharashtra University" (Q1) and "MSET" (Q4).<br/>• **False Preference Limit**: Claimed CAP form is capped at 5 preferences (actual: 300) (Q1).<br/>• **Zero-Shot Abstention**: Generated mock College A/B/C cards instead of halting on missing fee/district data (Q5). |
| **Reference Model**<br/>(`qwen2.5:7b`)<br/>*Overall Score: 33.0/50 (66%)* | • **Higher Baseline Score**: Achieved 33.0 / 50 (66.0%) across the benchmark.<br/>• **Curricular Depth**: Thoroughly explained hardware vs. software trade-offs across CS, IT, and AI&DS (Q2).<br/>• **Monotonic Ordering**: Correctly ordered percentile thresholds without arithmetic inversions (Q3). | • **Critical Geographical Hallucination**: Recommended Shri Ramdeobaba (SRCEM) in Nagpur (700+ km away) for a candidate requesting a short commute in Pune (Q4).<br/>• **Administrative Confusion**: Falsely claimed MSBTE conducts CAP engineering admissions and capped preferences at 15 colleges (Q1).<br/>• **High Latency**: 37.92s average response time on host CPU.<br/>• **Zero-Shot Abstention**: Also invented mock College A/B/C cards with ₹1.2L–₹1.4L fees instead of refusing without evidence (Q5). |

---

## 7. Numeric Comparison Error Analysis: The `92.40 < 95.00` Failure

In Question 3, AI-CON produced the following line:
> `- College B: You are eligible (92.40 > 95)`

### Root Cause Analysis
1. **Tokenization Disconnect**: Modern byte-pair tokenizers split `92.40` into `['92', '.', '40']` and `95` into `['95']`. Autoregressive attention does not execute an arithmetic floating-point comparator.
2. **Pattern Matching vs. Calculation**: The model regurgitated the lexical pattern `You are eligible (<X> > <Y>)` without evaluating the underlying boolean expression.
3. **Implication for Admissions**: In real admissions, misinforming a 92.40 percentile candidate that they qualify for a 95.00 cutoff wastes one of their crucial early CAP preference codes.
4. **Mandatory Remedy**: **Never allow an LLM to compare percentiles.** Comparisons must be computed deterministically in Python:
   ```python
   def evaluate_cutoff(student_pct: float, cutoff_pct: float) -> str:
       if student_pct >= cutoff_pct:
           return "ELIGIBLE"
       return "INELIGIBLE"
   ```

---

## 8. Error Taxonomy & Severity Levels

| Severity | Category | Example from Benchmark | Risk to Student |
|:---|:---|:---|:---|
| **CRITICAL** | Mathematical Inversion | AI-CON stating `92.40 > 95` makes student eligible. | Student applies for unreachable college and loses seat. |
| **CRITICAL** | Geographical Hallucination | Reference model placing Nagpur's SRCEM in central Pune. | Student chooses college with impossible 700 km daily commute. |
| **HIGH** | Regulatory Authority Fabrication | AI-CON inventing "MSET" and "Maharashtra University". | Student navigates to fraudulent or non-existent portals. |
| **HIGH** | False Option Limits | AI-CON stating preferences are capped at 5 (actual: 300). | Student severely under-utilizes CAP preference strategy. |
| **MEDIUM** | Mock Card Generation | Both models inventing College A (₹1.2L) when told to abstain. | User mistakes mock examples for real recommendations. |
| **LOW** | Minor Nomenclature Splits | AI-CON treating AI and Data Science as separate degrees. | Slight confusion regarding curriculum structure. |

---

## 9. Recommended Production Architecture: Hybrid Deterministic-Generative Pipeline

To eliminate hallucinations and mathematical errors, AI-CON must enforce strict separation across four tiers:

```
[Student Inquiries] 
        │
        ▼
[Intent & Entity Resolver] ─── (Ambiguity Detection)
        │
   ┌────┴──────────────────────────────┐
   ▼                                   ▼
[CutoffAgent]                  [CollegeInfoAgent]
(Exact SQLite/Parquet DB)       (ChromaDB Vector Store)
   │                                   │
   ├───────► [Tabular ML Models]       │
   │         (HistGradientBoosting)    │
   │                                   │
   └───────────────┬───────────────────┘
                   ▼
         [Deterministic Evidence]
                   │
                   ▼
       [LLM Counselling Assistant]
       (Grounded Synthesis & Explanation Only)
                   │
                   ▼
       [Student Decision Support]
```

### Architectural Responsibilities
1. **Tier 1 (CutoffAgent)**: Performs exact database lookups. Zero LLM guessing.
2. **Tier 2 (CollegeInfoAgent)**: Performs vector retrieval on verified college profiles.
3. **Tier 3 (Tabular ML Models)**: Generates regression predictions on closing ranks/percentiles with calibrated confidence intervals.
4. **Tier 4 (LLM Assistant)**: Translates structured evidence into accessible guidance while citing exact evidence IDs.

---

## 10. Illustrative Python Safeguards & Deterministic Guardrails

```python
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass
class CutoffValidationResult:
    student_percentile: float
    cutoff_percentile: float
    is_attainable: bool
    margin_percentile: float
    admissions_tier: str  # 'SAFE', 'REALISTIC', 'REACH', 'UNATTAINABLE'

def compare_cutoff_statistically(student_pct: float, cutoff_pct: float) -> CutoffValidationResult:
    \"\"\"Strict floating-point comparison preventing LLM arithmetic hallucination.\"\"\"
    margin = round(student_pct - cutoff_pct, 4)
    is_attainable = margin >= 0.0
    
    if margin >= 2.0:
        tier = "SAFE"
    elif margin >= 0.0:
        tier = "REALISTIC"
    elif margin >= -2.5:
        tier = "REACH"
    else:
        tier = "UNATTAINABLE"
        
    return CutoffValidationResult(
        student_percentile=student_pct,
        cutoff_percentile=cutoff_pct,
        is_attainable=is_attainable,
        margin_percentile=margin,
        admissions_tier=tier,
    )

def verify_maharashtra_category_rules(category: str, has_validity: bool, has_ncl: bool) -> Dict[str, Any]:
    \"\"\"Enforce statutory Maharashtra reservation validity conditions.\"\"\"
    cat = category.upper().strip()
    if cat in ("OBC", "VJ/DT", "NT-A", "NT-B", "NT-C", "NT-D", "SBC", "SEBC"):
        if not (has_validity and has_ncl):
            return {"eligible": False, "reason": "Requires both Caste Validity and Non-Creamy Layer valid to March 31."}
    elif cat in ("SC", "ST"):
        if not has_validity:
            return {"eligible": False, "reason": "Requires Caste/Tribe Validity Certificate."}
    return {"eligible": True, "reason": "Statutory documents verified."}
```

---

## 11. Testing Roadmap & Automated Regression Tests

| Test Suite | Target Component | Sample Count | Passing Threshold |
|:---|:---|:---:|:---:|
| **Unit Regression Suite** | Resolvers, rules engines, cutoff parsers | 111 unit tests | 100% pass (0 failures) |
| **Numeric Comparator Gate** | Synthetic percentile inequalities (X vs Y) | 5,000 pairs | 100% exact boolean accuracy |
| **Abstention Stress Gate** | Missing branch/quota query handling | 1,000 unoffered queries | 100% status='unavailable' |
| **Geographical Proximity Gate** | District and commute validation | 1,041 college coordinates | 0 inter-district commute errors |

---

## 12. Release-Readiness Assessment & Recommendations

| Readiness Gate | Criteria | Status | Required Action |
|:---|:---|:---:|:---|
| **Gate 1: Unit Tests** | 111 tests in repository suite | **PASSED** (109 passed, 2 skipped) | Maintain continuous regression runs. |
| **Gate 2: Tabular Predictor** | MAE & R² on 15,000 held-out test rows | **PASSED** ($R^2 = 0.5808$, MAE = 28,259) | Verified in `model_artifacts/`. |
| **Gate 3: Numerical Guardrails** | Deterministic cutoff comparison | **FAILED in LLM** | Must bind `CutoffAgent` before LLM generation. |
| **Gate 4: Abstention Gates** | Hard refusal without data | **PARTIAL** | Train 1,500+ SFT abstention pairs. |
| **Gate 5: Model Publishing** | Hugging Face private repository | **PREPARED** | Upload only after GPU fine-tuning completes. |

---

## 13. Evidence Limitations & Audit Disclosures

1. **Execution Environment**: Testing was conducted on Windows 11 with CPU-mode PyTorch (`2.14.1+cpu`). Although the host contains an NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM), full GPU QLoRA fine-tuning was held pending installation of CUDA-enabled PyTorch (`cu121`).
2. **Source Data Authority**: All scores, verbatim answers, and latency metrics are anchored strictly to the empirical benchmark recorded in `model_artifacts/five_level_test_results.json`.
3. **No Admission Guarantees**: Historical cutoff records reflect past applicant distributions and never constitute legal or guaranteed admission outcomes.

---

## 14. Appendix A: Benchmark Configuration & Runtime Environment Specs

| Parameter | Specification / Environment Value |
|:---|:---|
| **Host Operating System** | Windows 11 Enterprise (Build 10.0.26100) |
| **Hardware Platform** | Intel Core / AMD Ryzen Host CPU, NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM) |
| **Python Virtual Environment** | Python 3.10.11 at `model_rag_agent_plan/.venv` |
| **Inference Server** | Ollama local REST engine (`http://localhost:11434`) |
| **AI-CON Model** | `qwen2.5-aicon:latest` (Qwen2 3B, Q5_K_M GGUF, 36 layers, 2048 dim) |
| **Reference Model** | `qwen2.5:7b` (Qwen2 7B, Q4_K_M GGUF, 28 layers, 3584 dim) |
| **Sampling Configuration** | `temperature = 0.0` (deterministic greedy), `seed = 42`, `top_p = 1.0` |
| **Benchmark Script** | `scripts/run_5_level_test.py` |
| **Benchmark Artifact** | `model_artifacts/five_level_test_results.json` (43,622 bytes) |

---

## 15. Appendix B: Raw Evaluation Notes & Verification Data

| Target Item | Official Reference / Authority | Verification Status |
|:---|:---|:---:|
| **CAP Authority & Rules** | State Common Entrance Test Cell, Maharashtra - Information Brochure 2024-25 | Verified (Sole statutory body) |
| **Option Form Capacity** | CET Cell Rule 9(1) - Candidates may enter up to 300 choice codes | Verified (Not 5 or 15) |
| **Cutoff Database Scale** | 181,137 official CAP cutoff records across 2023-24 and 2024-25 | Verified in SQLite/Parquet DB |
| **College Profile Directory** | 1,041 participating engineering colleges indexed with university & district | Verified in ChromaDB vector store |
| **Tabular Model Metrics** | Closing Rank $R^2 = 0.5808$, Percentile $R^2 = 0.5401$ on 15,000 test split | Verified in `model_artifacts/` |
"""
    md_path.write_text(md_text, encoding="utf-8")
    print(f"Saved Markdown report to: {md_path}")


def build_pdf_report(data: List[Dict[str, Any]], pdf_path: Path):
    """Build the comprehensive ~20-page PDF report using ReportLab."""
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=45,
        bottomMargin=50,
    )

    styles = getSampleStyleSheet()

    # Custom Color Palette
    PRIMARY = colors.HexColor("#1B365D")  # Deep Navy
    SECONDARY = colors.HexColor("#335C67")  # Slate Blue
    ACCENT_RED = colors.HexColor("#991B1B")  # Crimson
    ACCENT_GREEN = colors.HexColor("#065F46")  # Forest Green
    TEXT_DARK = colors.HexColor("#1E293B")  # Charcoal
    BG_LIGHT = colors.HexColor("#F8FAFC")  # Light Slate
    BORDER_COLOR = colors.HexColor("#CBD5E1")

    # Typography Styles
    style_cover_title = ParagraphStyle(
        "CoverTitle",
        fontName="Helvetica-Bold",
        fontSize=26,
        leading=32,
        textColor=PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=12,
    )

    style_cover_subtitle = ParagraphStyle(
        "CoverSubtitle",
        fontName="Helvetica",
        fontSize=13,
        leading=18,
        textColor=SECONDARY,
        alignment=TA_CENTER,
        spaceAfter=24,
    )

    style_h1 = ParagraphStyle(
        "ReportH1",
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=PRIMARY,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True,
    )

    style_h2 = ParagraphStyle(
        "ReportH2",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=SECONDARY,
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True,
    )

    style_h3 = ParagraphStyle(
        "ReportH3",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=TEXT_DARK,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True,
    )

    style_body = ParagraphStyle(
        "ReportBody",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=TEXT_DARK,
        spaceAfter=6,
        alignment=TA_JUSTIFY,
    )

    style_body_bold = ParagraphStyle(
        "ReportBodyBold",
        parent=style_body,
        fontName="Helvetica-Bold",
    )

    style_callout = ParagraphStyle(
        "ReportCallout",
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        leading=12.5,
        textColor=PRIMARY,
    )

    style_code = ParagraphStyle(
        "ReportCode",
        fontName="Courier",
        fontSize=6.8,
        leading=8.8,
        textColor=colors.HexColor("#0F172A"),
        backColor=colors.HexColor("#F8FAFC"),
        borderColor=colors.HexColor("#CBD5E1"),
        borderWidth=0.75,
        borderPadding=5,
        spaceBefore=3,
        spaceAfter=5,
    )

    style_code_aicon = ParagraphStyle(
        "ReportCodeAicon",
        fontName="Courier",
        fontSize=6.8,
        leading=8.8,
        textColor=colors.HexColor("#0F172A"),
        backColor=colors.HexColor("#F1F5F9"),
        borderColor=colors.HexColor("#94A3B8"),
        borderWidth=0.75,
        borderPadding=5,
        spaceBefore=3,
        spaceAfter=5,
    )

    style_code_ref = ParagraphStyle(
        "ReportCodeRef",
        fontName="Courier",
        fontSize=6.8,
        leading=8.8,
        textColor=colors.HexColor("#0F172A"),
        backColor=colors.HexColor("#F8FAFC"),
        borderColor=colors.HexColor("#CBD5E1"),
        borderWidth=0.75,
        borderPadding=5,
        spaceBefore=3,
        spaceAfter=5,
    )

    style_table_cell = ParagraphStyle(
        "ReportTableCell",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=TEXT_DARK,
    )

    style_table_cell_bold = ParagraphStyle(
        "ReportTableCellBold",
        parent=style_table_cell,
        fontName="Helvetica-Bold",
    )

    style_table_cell_center = ParagraphStyle(
        "ReportTableCellCenter",
        parent=style_table_cell,
        alignment=TA_CENTER,
    )

    style_table_header = ParagraphStyle(
        "ReportTableHeader",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    story = []

    # =========================================================================
    # 1. COVER PAGE
    # =========================================================================
    story.append(Spacer(1, 40))
    story.append(Paragraph("AI-CON MODEL EVALUATION REPORT", style_cover_title))
    story.append(
        Paragraph(
            "Empirical Comparative Assessment of AI-CON vs. Qwen 2.5 7B<br/>"
            "on the 5-Level MHT-CET Engineering Admissions Counselling Benchmark",
            style_cover_subtitle,
        )
    )
    story.append(HRFlowable(width="80%", thickness=2, color=PRIMARY, spaceAfter=30))

    cover_meta = [
        [
            Paragraph("<b>Target System:</b>", style_table_cell),
            Paragraph("AI-CON (Maharashtra MHT-CET Decision-Support)", style_table_cell),
        ],
        [
            Paragraph("<b>Evaluated Models:</b>", style_table_cell),
            Paragraph("AI-CON (`qwen2.5-aicon:latest`) vs. Reference (`qwen2.5:7b`)", style_table_cell),
        ],
        [
            Paragraph("<b>Benchmark Scope:</b>", style_table_cell),
            Paragraph("5 Progressive Tiers (Level 1 Easy to Level 5 Extremely Hard)", style_table_cell),
        ],
        [
            Paragraph("<b>Overall Outcome:</b>", style_table_cell),
            Paragraph("AI-CON: <b>29.5 / 50 (59%)</b> | Reference: <b>33.0 / 50 (66%)</b>", style_table_cell),
        ],
        [
            Paragraph("<b>Key Recommendation:</b>", style_table_cell),
            Paragraph("Mandatory Hybrid Architecture (Deterministic CutoffEngine + LLM Explanation)", style_table_cell),
        ],
        [
            Paragraph("<b>Evaluation Date:</b>", style_table_cell),
            Paragraph(f"{datetime.now().strftime('%B %d, %Y')}", style_table_cell),
        ],
        [
            Paragraph("<b>Report Author:</b>", style_table_cell),
            Paragraph("Senior Python / ML Admissions Evaluator", style_table_cell),
        ],
    ]
    meta_table = Table(cover_meta, colWidths=[150, 320])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    story.append(meta_table)

    story.append(Spacer(1, 40))
    notice_text = (
        "<b>LEGAL & AUDIT NOTICE:</b> Historical admission cutoffs, closing ranks, and percentiles "
        "documented in this report serve solely as empirical reference observations. They do not "
        "constitute an absolute guarantee of college admission under any circumstances. Official "
        "allotments are governed strictly by the State Common Entrance Test Cell, Maharashtra."
    )
    notice_p = Table([[Paragraph(notice_text, style_callout)]], colWidths=[515])
    notice_p.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#D97706")),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    story.append(notice_p)

    story.append(PageBreak())

    # =========================================================================
    # 2. EXECUTIVE SUMMARY & BENCHMARK SCORECARD
    # =========================================================================
    story.append(Paragraph("1. Executive Summary", style_h1))
    story.append(
        Paragraph(
            "This report delivers an exhaustive, evidence-based technical evaluation of the <b>AI-CON</b> "
            "educational counselling model against the stock <b>Qwen 2.5 7B</b> reference model. "
            "Both models were subjected to an identical 5-level progressive testing protocol designed to evaluate "
            "admissions knowledge across Maharashtra Centralized Admission Process (CAP) rules, historical cutoff "
            "interpretations, conflicting student preferences, and severe multi-constraint counselling.",
            style_body,
        )
    )
    story.append(
        Paragraph(
            "<b>Final Scores:</b> AI-CON scored <b>29.5 / 50 (59.0%)</b> while the reference model achieved "
            "<b>33.0 / 50 (66.0%)</b>. While AI-CON showed superior conceptual restraint in distinguishing statutory "
            "eligibility from admission guarantees, it suffered from a critical mathematical inequality failure "
            "in Level 3 (evaluating <code>92.40 > 95</code> as eligible). Conversely, the reference model suffered "
            "from severe geographical hallucinations, recommending a college in Nagpur (700 km away) for a student "
            "seeking a short commute within Pune.",
            style_body,
        )
    )

    story.append(Spacer(1, 10))
    story.append(Paragraph("Executive Benchmark Scorecard", style_h2))

    summary_headers = [
        Paragraph("<b>Question</b>", style_table_header),
        Paragraph("<b>Difficulty</b>", style_table_header),
        Paragraph("<b>AI-CON (/10)</b>", style_table_header),
        Paragraph("<b>Ref (/10)</b>", style_table_header),
        Paragraph("<b>Main Factual Error</b>", style_table_header),
        Paragraph("<b>Missing Info Handling</b>", style_table_header),
    ]

    summary_rows = [
        summary_headers,
        [
            Paragraph("<b>Q1</b>", style_table_cell_center),
            Paragraph("Level 1: Easy", style_table_cell),
            Paragraph("<b>4.5</b>", style_table_cell_center),
            Paragraph("<b>6.0</b>", style_table_cell_center),
            Paragraph("AI-CON: 5-pref limit, 'Maharashtra Univ' authority.<br/>Ref: MSBTE conducts CAP, 15-college limit.", style_table_cell),
            Paragraph("AI-CON: Asked for rank & seats.<br/>Ref: Asked for exact score & HSC marks.", style_table_cell),
        ],
        [
            Paragraph("<b>Q2</b>", style_table_cell_center),
            Paragraph("Level 2: Moderate", style_table_cell),
            Paragraph("<b>7.5</b>", style_table_cell_center),
            Paragraph("<b>8.0</b>", style_table_cell_center),
            Paragraph("AI-CON: Split AI and DS degree nomenclature.<br/>Ref: None significant.", style_table_cell),
            Paragraph("Both models distinguished general industry demand from absence of college data.", style_table_cell),
        ],
        [
            Paragraph("<b>Q3</b>", style_table_cell_center),
            Paragraph("Level 3: Hard", style_table_cell),
            Paragraph("<b>5.0</b>", style_table_cell_center),
            Paragraph("<b>7.0</b>", style_table_cell_center),
            Paragraph("AI-CON: Inverted inequality (<code>92.40 > 95</code>).<br/>Ref: Invented mock numbers.", style_table_cell),
            Paragraph("Both identified missing category, quota, and round dimensions.", style_table_cell),
        ],
        [
            Paragraph("<b>Q4</b>", style_table_cell_center),
            Paragraph("Level 4: Very Hard", style_table_cell),
            Paragraph("<b>6.5</b>", style_table_cell_center),
            Paragraph("<b>5.5</b>", style_table_cell_center),
            Paragraph("AI-CON: Fabricated 'MSET' university.<br/>Ref: Placed Nagpur college (SRCEM) in Pune.", style_table_cell),
            Paragraph("AI-CON: Refused to assume reserved status.<br/>Ref: Prematurely assigned quotas.", style_table_cell),
        ],
        [
            Paragraph("<b>Q5</b>", style_table_cell_center),
            Paragraph("Level 5: Extremely Hard", style_table_cell),
            Paragraph("<b>6.0</b>", style_table_cell_center),
            Paragraph("<b>6.5</b>", style_table_cell_center),
            Paragraph("Both models violated negative constraint by generating mock College A/B/C cards.", style_table_cell),
            Paragraph("AI-CON: Outstanding eligibility vs guarantee definitions.<br/>Ref: Thorough audit process.", style_table_cell),
        ],
        [
            Paragraph("<b>TOTAL</b>", style_table_cell_center),
            Paragraph("<b>All 5 Levels</b>", style_table_cell_bold),
            Paragraph("<b>29.5 / 50</b>", style_table_cell_bold),
            Paragraph("<b>33.0 / 50</b>", style_table_cell_bold),
            Paragraph("<b>AI-CON: 59.0%</b>", style_table_cell_bold),
            Paragraph("<b>Reference: 66.0%</b>", style_table_cell_bold),
        ],
    ]

    table_summary = Table(
        summary_rows, colWidths=[35, 75, 55, 55, 155, 140], repeatRows=1
    )
    table_summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, BG_LIGHT]),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2E8F0")),
            ]
        )
    )
    story.append(table_summary)

    story.append(PageBreak())

    # =========================================================================
    # 3. PROJECT OVERVIEW & TESTING OBJECTIVES
    # =========================================================================
    story.append(Paragraph("2. Project Overview & Testing Objectives", style_h1))
    story.append(
        Paragraph(
            "<b>AI-CON</b> is designed as an automated, evidence-grounded decision-support system for candidates "
            "participating in the Maharashtra MHT-CET Centralized Admission Process (CAP). The engineering admission "
            "landscape in Maharashtra is uniquely complex, encompassing over 1,041 participating engineering institutions, "
            "multiple distinct universities, and tens of thousands of course-seat quota combinations.",
            style_body,
        )
    )

    story.append(Paragraph("Key Complexity Dimensions in MHT-CET Admissions", style_h2))
    story.append(
        Paragraph(
            "• <b>Academic Year Variations:</b> Cutoffs fluctuate significantly between admission years based on applicant volume and CET difficulty.<br/>"
            "• <b>Multi-Round Dynamics:</b> CAP spans Rounds 1, 2, and 3, with cutoffs exhibiting dynamic seat absorption.<br/>"
            "• <b>Quota Classifications:</b> Seats are bifurcated into Home University (HU), Other than Home University (OHU), and State Level (SL).<br/>"
            "• <b>Statutory Reservations:</b> Distinct allocations for Open, SC, ST, VJ/DT, NT-A/B/C/D, OBC, SBC, SEBC, EWS, and TFWS.<br/>"
            "• <b>Sub-Quota Categories:</b> PWD (Persons with Disabilities), DEF (Defense personnel children), and Female (30% horizontal reservation).",
            style_body,
        )
    )

    story.append(Spacer(1, 10))
    story.append(Paragraph("3. Models Evaluated & Methodology", style_h1))
    story.append(
        Paragraph(
            "The evaluation pitted the locally deployed AI-CON model against the reference Qwen 2.5 7B foundation model "
            "under identical, deterministic parameters. Inference was executed via the local Ollama engine at temperature 0.0 "
            "to prevent stochastic sampling variations.",
            style_body,
        )
    )

    specs = [
        [
            Paragraph("<b>Parameter</b>", style_table_header),
            Paragraph("<b>AI-CON (`qwen2.5-aicon:latest`)</b>", style_table_header),
            Paragraph("<b>Reference Model (`qwen2.5:7b`)</b>", style_table_header),
        ],
        [
            Paragraph("<b>Base Architecture</b>", style_table_cell),
            Paragraph("Qwen2 3B (36 transformer layers, 2048 hidden dim)", style_table_cell),
            Paragraph("Qwen2 7B (28 transformer layers, 3584 hidden dim)", style_table_cell),
        ],
        [
            Paragraph("<b>Serving Precision</b>", style_table_cell),
            Paragraph("GGUF Q5_K_M (5-bit K-quant medium)", style_table_cell),
            Paragraph("GGUF Q4_K_M (4-bit K-quant medium)", style_table_cell),
        ],
        [
            Paragraph("<b>System Instructions</b>", style_table_cell),
            Paragraph("Strict evidence grounding, bracketed citations, anti-hallucination", style_table_cell),
            Paragraph("Expert educational counselling assistant prompt", style_table_cell),
        ],
        [
            Paragraph("<b>Avg Response Latency</b>", style_table_cell),
            Paragraph("20.44 seconds (CPU multithreaded)", style_table_cell),
            Paragraph("37.92 seconds (CPU multithreaded)", style_table_cell),
        ],
    ]
    table_specs = Table(specs, colWidths=[120, 195, 200])
    table_specs.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SECONDARY),
                ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
            ]
        )
    )
    story.append(table_specs)

    story.append(PageBreak())

    # =========================================================================
    # 4. QUESTION-BY-QUESTION IN-DEPTH ANALYSIS (Q1 TO Q5)
    # =========================================================================
    for idx, item in enumerate(data, 1):
        qid = item["id"]
        diff = item["difficulty"]
        q_text = item["question"]
        a_ans = item["aicon"]["answer"]
        r_ans = item["reference"]["answer"]
        a_lat = item["aicon"]["latency_sec"]
        r_lat = item["reference"]["latency_sec"]

        story.append(Paragraph(f"4.{idx} {qid}: {diff}", style_h1))
        story.append(Paragraph("<b>Exact Question Asked:</b>", style_h3))

        q_box = Table([[Paragraph(f"<i>{q_text}</i>", style_body)]], colWidths=[515])
        q_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
                    ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(q_box)
        story.append(Spacer(1, 8))

        # AI-CON Output Box
        story.append(
            Paragraph(
                f"<b>Complete AI-CON Answer (Verbatim, Latency: {a_lat}s):</b>",
                style_h3,
            )
        )
        story.extend(make_code_flowables(a_ans, style_code_aicon))
        story.append(Spacer(1, 6))

        # Reference Output Box
        story.append(
            Paragraph(
                f"<b>Complete Reference Model Answer (Verbatim, Latency: {r_lat}s):</b>",
                style_h3,
            )
        )
        story.extend(make_code_flowables(r_ans, style_code_ref))
        story.append(Spacer(1, 8))

        # Critical Critique & Audit
        story.append(Paragraph("Evaluator Audit & Point-by-Point Findings", style_h2))

        critiques = {
            "Q1": (
                "• <b>Administrative Authority:</b> AI-CON cited 'Maharashtra University' while the reference model "
                "cited 'MSBTE'. Both are factually incorrect. The sole statutory body conducting engineering CAP is the "
                "<b>State Common Entrance Test Cell, Maharashtra</b>.<br/>"
                "• <b>Option Form Capacity:</b> AI-CON claimed preferences are ranked from 1 to 5. The reference model "
                "claimed a limit of 15 colleges with 3 branches each. Both are incorrect. Official CET Cell Information "
                "Brochure Rule 9(1) permits candidates to submit up to <b>300 choice codes</b>.<br/>"
                "• <b>Verification Sequence:</b> The reference model erroneously stated that document verification happens "
                "<i>after</i> allocation at the allotted college. In reality, e-Scrutiny or physical Scrutiny Center verification "
                "occurs before merit list finalization."
            ),
            "Q2": (
                "• <b>Curriculum Differentiation:</b> Both models accurately mapped the hardware/architecture focus of "
                "Computer Engineering vs the software/networking focus of Information Technology.<br/>"
                "• <b>Nomenclature Nuance:</b> AI-CON divided AI and Data Science into two standalone theoretical fields, "
                "whereas Maharashtra universities offer an integrated 4-year degree titled <i>Artificial Intelligence and Data Science</i>.<br/>"
                "• <b>Data vs. Trend Demarcation:</b> Both models successfully adhered to instructions by refusing to fabricate "
                "audited placement statistics or institutional median salaries without primary verification sources."
            ),
            "Q3": (
                "• <b>CRITICAL INEQUALITY INVERSION:</b> AI-CON committed a severe failure of numerical reasoning:<br/>"
                "&nbsp;&nbsp;&nbsp;&nbsp;<code>- College B: You are eligible (92.40 > 95)</code><br/>"
                "92.40 is strictly less than 95.00. This error would cause a candidate to waste a preference slot on an unattainable college.<br/>"
                "• <b>Negative Constraint Violation:</b> Both models violated the instruction not to invent cutoff values by "
                "introducing hypothetical mock colleges (College A, B, C) with arbitrary figures instead of strictly stating that "
                "the necessary data was unsupplied."
            ),
            "Q4": (
                "• <b>CRITICAL GEOGRAPHICAL HALLUCINATION:</b> The reference model recommended <i>Shri Ramdeobaba College "
                "of Engineering and Management (SRCEM)</i> for a student demanding a short commute in Pune. SRCEM is in <b>Nagpur</b>, "
                "more than 700 km east of Pune.<br/>"
                "• <b>Institutional Authority Fabrication:</b> AI-CON stated cutoffs should be verified from 'Maharashtra University "
                "of Engineering and Technology (MSET)'—a non-existent institution.<br/>"
                "• <b>Reserved Category Restraint:</b> AI-CON correctly refused to treat unverified category eligibility as established, "
                "demanding Caste Validity and Non-Creamy Layer documentation prior to seat matrix matching."
            ),
            "Q5": (
                "• <b>Eligibility vs. Likelihood vs. Guarantee:</b> AI-CON delivered an outstanding conceptual breakdown in Step 6, "
                "properly separating statutory eligibility from statistical likelihood and absolute admission guarantee.<br/>"
                "• <b>Mock Shortlist Generation:</b> Both models failed the hard negative constraint by generating fictitious "
                "cards for College A, B, and C with arbitrary fees (₹1.2L to ₹1.4L). The models should have refused to generate a shortlist "
                "until domicile, category, and specific fee approvals were provided."
            ),
        }

        story.append(Paragraph(critiques[qid], style_body))

        # Question Score Table
        q_scores = {
            "Q1": ("4.5", "6.0", "1.0 / 3", "1.5 / 3", "1.0 / 2", "1.5 / 2", "1.0 / 2", "1.5 / 2", "1.0 / 2", "1.0 / 2", "0.5 / 1", "0.5 / 1"),
            "Q2": ("7.5", "8.0", "2.5 / 3", "2.5 / 3", "1.5 / 2", "2.0 / 2", "1.5 / 2", "1.5 / 2", "1.5 / 2", "1.5 / 2", "0.5 / 1", "0.5 / 1"),
            "Q3": ("5.0", "7.0", "1.0 / 3", "2.5 / 3", "1.0 / 2", "1.5 / 2", "1.5 / 2", "1.5 / 2", "1.0 / 2", "1.0 / 2", "0.5 / 1", "0.5 / 1"),
            "Q4": ("6.5", "5.5", "1.5 / 3", "0.5 / 3", "1.5 / 2", "1.5 / 2", "1.5 / 2", "1.5 / 2", "1.5 / 2", "1.0 / 2", "0.5 / 1", "1.0 / 1"),
            "Q5": ("6.0", "6.5", "2.0 / 3", "2.0 / 3", "1.5 / 2", "1.5 / 2", "1.0 / 2", "1.5 / 2", "1.0 / 2", "1.0 / 2", "0.5 / 1", "0.5 / 1"),
        }
        qs = q_scores[qid]

        score_data = [
            [
                Paragraph("<b>Rubric Dimension</b>", style_table_header),
                Paragraph("<b>AI-CON Score</b>", style_table_header),
                Paragraph("<b>Reference Score</b>", style_table_header),
            ],
            [Paragraph("Factual Correctness (0–3)", style_table_cell), Paragraph(qs[2], style_table_cell_center), Paragraph(qs[3], style_table_cell_center)],
            [Paragraph("Reasoning & Comparison (0–2)", style_table_cell), Paragraph(qs[4], style_table_cell_center), Paragraph(qs[5], style_table_cell_center)],
            [Paragraph("Completeness (0–2)", style_table_cell), Paragraph(qs[6], style_table_cell_center), Paragraph(qs[7], style_table_cell_center)],
            [Paragraph("Handling of Uncertainty (0–2)", style_table_cell), Paragraph(qs[8], style_table_cell_center), Paragraph(qs[9], style_table_cell_center)],
            [Paragraph("Clear Explanation (0–1)", style_table_cell), Paragraph(qs[10], style_table_cell_center), Paragraph(qs[11], style_table_cell_center)],
            [Paragraph("<b>TOTAL SCORE</b>", style_table_cell_bold), Paragraph(f"<b>{qs[0]} / 10</b>", style_table_cell_bold), Paragraph(f"<b>{qs[1]} / 10</b>", style_table_cell_bold)],
        ]
        score_tab = Table(score_data, colWidths=[215, 150, 150])
        score_tab.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                    ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, BG_LIGHT]),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2E8F0")),
                ]
            )
        )
        story.append(score_tab)
        story.append(Spacer(1, 14))
        story.append(HRFlowable(width="100%", thickness=0.75, color=BORDER_COLOR, spaceAfter=14))

    story.append(PageBreak())

    # =========================================================================
    # 5. MODEL STRENGTHS & WEAKNESSES COMPARISON
    # =========================================================================
    story.append(Paragraph("5. Model Strengths & Weaknesses Comparison", style_h1))
    story.append(
        Paragraph(
            "An architectural and behavioral evaluation reveals contrasting performance profiles between "
            "the specialized AI-CON model (Qwen 2.5 3B) and the generic Reference model (Qwen 2.5 7B):",
            style_body,
        )
    )

    strengths_data = [
        [
            Paragraph("<b>Model</b>", style_table_header),
            Paragraph("<b>Core Strengths</b>", style_table_header),
            Paragraph("<b>Observed Vulnerabilities</b>", style_table_header),
        ],
        [
            Paragraph("<b>AI-CON</b><br/>(<code>qwen2.5-aicon:latest</code>)<br/><b>Score: 29.5/50</b>", style_table_cell),
            Paragraph(
                "• <b>Conceptual Rigor:</b> Flawlessly separates statutory eligibility from statistical likelihood and admission guarantees (Q5 Step 6).<br/>"
                "• <b>Reservation Discipline:</b> Strictly requires Caste Validity Certificate and Non-Creamy Layer (NCL) before evaluating reserved quotas (Q4).<br/>"
                "• <b>Fast Inference:</b> 20.44s avg latency (1.85x faster than 7B reference).<br/>"
                "• <b>Compact Footprint:</b> Fits in ~2.5 GB RAM on consumer hardware.",
                style_table_cell,
            ),
            Paragraph(
                "• <b>Arithmetic Inversion:</b> Critical failure evaluating <code>92.40 > 95</code> as eligible (Q3).<br/>"
                "• <b>Authority Fabrication:</b> Invented fictitious bodies 'Maharashtra University' (Q1) and 'MSET' (Q4).<br/>"
                "• <b>Preference Limit Truncation:</b> Falsely claimed choice codes are capped at 5 preferences (actual: 300) (Q1).<br/>"
                "• <b>Zero-Shot Abstention:</b> Invented mock College A/B/C cards instead of refusing without evidence (Q5).",
                style_table_cell,
            ),
        ],
        [
            Paragraph("<b>Reference</b><br/>(<code>qwen2.5:7b</code>)<br/><b>Score: 33.0/50</b>", style_table_cell),
            Paragraph(
                "• <b>Higher Baseline Score:</b> Scored 33.0/50 (66.0%) across all tiers.<br/>"
                "• <b>Curricular Depth:</b> Comprehensive analysis of hardware/software trade-offs across CS, IT, and AI&DS (Q2).<br/>"
                "• <b>Monotonic Ordering:</b> Correctly ordered percentile comparisons without arithmetic inversions (Q3).",
                style_table_cell,
            ),
            Paragraph(
                "• <b>CRITICAL GEOGRAPHICAL HALLUCINATION:</b> Placed Nagpur's SRCEM in Pune (700+ km away) for a short-commute student (Q4).<br/>"
                "• <b>Regulatory Confusion:</b> Claimed MSBTE conducts CAP and capped preferences at 15 colleges (Q1).<br/>"
                "• <b>High Latency:</b> 37.92s average response time on host CPU.<br/>"
                "• <b>Zero-Shot Abstention:</b> Also invented fictitious College A/B/C cards with ₹1.2L–₹1.4L fees (Q5).",
                style_table_cell,
            ),
        ],
    ]
    table_strengths = Table(strengths_data, colWidths=[95, 210, 210])
    table_strengths.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
            ]
        )
    )
    story.append(table_strengths)
    story.append(PageBreak())

    # =========================================================================
    # 6. ERROR TAXONOMY & SEVERITY CLASSIFICATION
    # =========================================================================
    story.append(Paragraph("6. Error Taxonomy & Failure Modes", style_h1))
    story.append(
        Paragraph(
            "To systemize quality assurance for future releases, all recorded model errors have been categorized "
            "into a rigorous 4-tier severity taxonomy based on potential real-world harm to student candidates.",
            style_body,
        )
    )

    taxonomy = [
        [
            Paragraph("<b>Severity</b>", style_table_header),
            Paragraph("<b>Error Type</b>", style_table_header),
            Paragraph("<b>Observed Failure Case</b>", style_table_header),
            Paragraph("<b>Candidate Impact</b>", style_table_header),
        ],
        [
            Paragraph("<b>CRITICAL</b>", style_table_cell_bold),
            Paragraph("Numerical Inversion", style_table_cell),
            Paragraph("AI-CON stating `92.40 > 95` makes student eligible.", style_table_cell),
            Paragraph("Wasting high-priority preference code on unreachable seat.", style_table_cell),
        ],
        [
            Paragraph("<b>CRITICAL</b>", style_table_cell_bold),
            Paragraph("Geographical Hallucination", style_table_cell),
            Paragraph("Reference model placing Nagpur's SRCEM in Pune.", style_table_cell),
            Paragraph("Unviable selection requiring 700 km daily transit.", style_table_cell),
        ],
        [
            Paragraph("<b>HIGH</b>", style_table_cell_bold),
            Paragraph("Authority Fabrication", style_table_cell),
            Paragraph("AI-CON inventing 'MSET' and 'Maharashtra Univ'.", style_table_cell),
            Paragraph("Confusion; navigating to unaccredited or non-existent sites.", style_table_cell),
        ],
        [
            Paragraph("<b>HIGH</b>", style_table_cell_bold),
            Paragraph("Option Limit Truncation", style_table_cell),
            Paragraph("AI-CON stating preference list is capped at 5.", style_table_cell),
            Paragraph("Candidate loses 295 potential backup options in CAP form.", style_table_cell),
        ],
        [
            Paragraph("<b>MEDIUM</b>", style_table_cell_bold),
            Paragraph("Fictitious Placeholder Generation", style_table_cell),
            Paragraph("Inventing College A, B, C with ₹1.2L fees when data missing.", style_table_cell),
            Paragraph("User misinterprets synthetic data as valid college options.", style_table_cell),
        ],
        [
            Paragraph("<b>LOW</b>", style_table_cell_bold),
            Paragraph("Nomenclature Division", style_table_cell),
            Paragraph("AI-CON treating AI and Data Science as separate degrees.", style_table_cell),
            Paragraph("Minor academic confusion regarding curriculum structure.", style_table_cell),
        ],
    ]
    table_tax = Table(taxonomy, colWidths=[65, 105, 185, 160])
    table_tax.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7F1D1D")),
                ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
            ]
        )
    )
    story.append(table_tax)

    story.append(Spacer(1, 12))
    story.append(Paragraph("7. Deep Dive: Numeric Comparison Failures", style_h1))
    story.append(
        Paragraph(
            "The error <code>92.40 > 95</code> in Level 3 illustrates why autoregressive language models "
            "must never be tasked with direct arithmetic evaluation. Transformer tokenizers decompose floating-point numbers "
            "into separate subword fragments (e.g., <code>'92'</code>, <code>'.'</code>, <code>'40'</code>). The model's "
            "attention heads predict the next token based on surface linguistic plausibility rather than mathematical logic.",
            style_body,
        )
    )
    story.append(
        Paragraph(
            "<b>Architectural Directive:</b> In AI-CON, all cutoff checks must be routed through deterministic Python "
            "comparators. The LLM's role must be strictly constrained to verbalizing verified comparisons provided in evidence.",
            style_body,
        )
    )

    story.append(PageBreak())

    # =========================================================================
    # 8. RECOMMENDED HYBRID ARCHITECTURE & CODE SAFEGUARDS
    # =========================================================================
    story.append(Paragraph("8. Recommended Hybrid Production Architecture", style_h1))
    story.append(
        Paragraph(
            "To guarantee 100% mathematical precision and eliminate geographical or regulatory hallucinations, "
            "AI-CON must enforce strict separation across four tiers:",
            style_body,
        )
    )

    arch_diagram = """
+-----------------------------------------------------------------------------------+
|                           STUDENT CONVERSATIONAL QUERY                            |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
|               TIER 1: INTENT & ENTITY RESOLVER (CollegeResolver)                  |
|  - Matches college names across 1,041 verified institutes (fuzzy & alias match)   |
|  - Flags ambiguous queries (e.g. "Government College") with NEEDS_CLARIFICATION   |
+-----------------------------------------------------------------------------------+
                                         │
                    ┌────────────────────┴────────────────────┐
                    ▼                                         ▼
+---------------------------------------+ +---------------------------------------+
|     TIER 2A: CUTOFF ENGINE            | |      TIER 2B: COLLEGE INFO ENGINE     |
|          (CutoffAgent)                | |         (CollegeInfoAgent)            |
| - Exact SQL/Parquet lookups           | | - ChromaDB vector index over 1,041    |
| - 181,137 verified official records   | |   verified college JSON profiles      |
| - Deterministic inequality evaluator  | | - Institutional affiliations & status |
+---------------------------------------+ +---------------------------------------+
                    │                                         │
                    ├────────────────────┐                    │
                    ▼                    ▼                    │
+------------------------------------+   │                    │
|   TIER 3: TABULAR ML PREDICTORS    |   │                    │
|     (HistGradientBoosting)         |   │                    │
| - Predicted closing rank           |   │                    │
| - Predicted closing percentile     |   │                    │
| - R^2 = 0.5808, MAE = 28,259       |   │                    │
+------------------------------------+   │                    │
                    │                    │                    │
                    └────────────────────┼────────────────────┘
                                         ▼
+-----------------------------------------------------------------------------------+
|                 IMMUTABLE DETERMINISTIC EVIDENCE PAYLOAD                          |
|  - Exact cutoff numbers with bracketed citations [2024-25:01002:...]             |
|  - Verified eligibility delta: (Student_Pct - Cutoff_Pct)                         |
|  - Affiliation, autonomy, district, fee concessions, and transport notes         |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
|            TIER 4: GENERATIVE LLM ASSISTANT (Qwen 3B LoRA Adapter)                |
|  - Generates clear, compassionate counselling advice strictly from evidence       |
|  - Never invents numbers or institutions; copies bracketed citations verbatim    |
|  - Hard abstention: returns STATUS: UNAVAILABLE if course is not offered          |
+-----------------------------------------------------------------------------------+
"""
    story.append(Preformatted(html.escape(arch_diagram.strip()), style_code))

    story.append(PageBreak())
    story.append(Paragraph("9. Illustrative Python Safeguards", style_h1))
    story.append(
        Paragraph(
            "Below are production-ready Python guardrail functions implementing deterministic cutoff comparisons, "
            "statutory document validation, and strict abstention enforcement:",
            style_body,
        )
    )

    code_safeguards = """from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass
class CutoffValidationResult:
    student_percentile: float
    cutoff_percentile: float
    is_attainable: bool
    margin_percentile: float
    admissions_tier: str  # 'SAFE', 'REALISTIC', 'REACH', 'UNATTAINABLE'

def compare_cutoff_statistically(student_pct: float, cutoff_pct: float) -> CutoffValidationResult:
    \"\"\"Strict floating-point comparison preventing LLM arithmetic hallucination.\"\"\"
    margin = round(student_pct - cutoff_pct, 4)
    is_attainable = margin >= 0.0
    
    if margin >= 2.0:
        tier = "SAFE"
    elif margin >= 0.0:
        tier = "REALISTIC"
    elif margin >= -2.5:
        tier = "REACH"
    else:
        tier = "UNATTAINABLE"
        
    return CutoffValidationResult(
        student_percentile=student_pct,
        cutoff_percentile=cutoff_pct,
        is_attainable=is_attainable,
        margin_percentile=margin,
        admissions_tier=tier
    )

def verify_maharashtra_category_rules(category: str, has_validity: bool, has_ncl: bool) -> Dict[str, Any]:
    \"\"\"Enforce statutory Maharashtra reservation validity conditions.\"\"\"
    cat = category.upper().strip()
    if cat in ("OBC", "VJ/DT", "NT-A", "NT-B", "NT-C", "NT-D", "SBC", "SEBC"):
        if not (has_validity and has_ncl):
            return {"eligible": False, "reason": "Requires both Caste Validity and Non-Creamy Layer valid to March 31."}
    elif cat in ("SC", "ST"):
        if not has_validity:
            return {"eligible": False, "reason": "Requires Caste/Tribe Validity Certificate."}
    return {"eligible": True, "reason": "Statutory documents verified."}
"""
    story.append(Preformatted(html.escape(code_safeguards.strip()), style_code))

    story.append(PageBreak())

    # =========================================================================
    # 10. TESTING ROADMAP, EVALUATION METRICS & RELEASE READINESS
    # =========================================================================
    story.append(Paragraph("10. Testing Roadmap & Automated Regression Tests", style_h1))
    story.append(
        Paragraph(
            "To safeguard against regression before release, the following multi-stage testing roadmap is established:",
            style_body,
        )
    )

    roadmap = [
        [
            Paragraph("<b>Test Suite</b>", style_table_header),
            Paragraph("<b>Target Component</b>", style_table_header),
            Paragraph("<b>Sample Count</b>", style_table_header),
            Paragraph("<b>Passing Threshold</b>", style_table_header),
        ],
        [
            Paragraph("Unit Regression Suite", style_table_cell),
            Paragraph("Resolvers, rules engines, cutoff parsers", style_table_cell),
            Paragraph("111 unit tests", style_table_cell),
            Paragraph("100% pass (0 failures)", style_table_cell),
        ],
        [
            Paragraph("Numeric Comparator Gate", style_table_cell),
            Paragraph("Synthetic percentile inequalities (X vs Y)", style_table_cell),
            Paragraph("5,000 pairs", style_table_cell),
            Paragraph("100% exact boolean accuracy", style_table_cell),
        ],
        [
            Paragraph("Abstention Stress Gate", style_table_cell),
            Paragraph("Missing branch/quota query handling", style_table_cell),
            Paragraph("1,000 unoffered queries", style_table_cell),
            Paragraph("100% status='unavailable'", style_table_cell),
        ],
        [
            Paragraph("Geographical Proximity Gate", style_table_cell),
            Paragraph("District and commute validation", style_table_cell),
            Paragraph("1,041 college coordinates", style_table_cell),
            Paragraph("0 inter-district commute errors", style_table_cell),
        ],
    ]
    table_roadmap = Table(roadmap, colWidths=[120, 155, 110, 130])
    table_roadmap.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SECONDARY),
                ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
            ]
        )
    )
    story.append(table_roadmap)

    story.append(Spacer(1, 14))
    story.append(Paragraph("11. Release Readiness & Quality Gates", style_h1))

    gates = [
        [
            Paragraph("<b>Quality Gate</b>", style_table_header),
            Paragraph("<b>Specification</b>", style_table_header),
            Paragraph("<b>Current Status</b>", style_table_header),
            Paragraph("<b>Release Recommendation</b>", style_table_header),
        ],
        [
            Paragraph("Gate 1: Unit Tests", style_table_cell),
            Paragraph("Repository unittest discover tests", style_table_cell),
            Paragraph("<b>PASSED</b> (109 passed, 2 skipped)", style_table_cell),
            Paragraph("Production Ready", style_table_cell),
        ],
        [
            Paragraph("Gate 2: Tabular Predictor", style_table_cell),
            Paragraph("HistGradientBoosting R² > 0.50 on 15k test", style_table_cell),
            Paragraph("<b>PASSED</b> (Rank: 0.58, Pct: 0.54)", style_table_cell),
            Paragraph("Production Ready", style_table_cell),
        ],
        [
            Paragraph("Gate 3: Cutoff Integrity", style_table_cell),
            Paragraph("Zero mathematical comparison errors", style_table_cell),
            Paragraph("<b>FAILED in Raw LLM</b>", style_table_cell),
            Paragraph("Enforce CutoffAgent mediation", style_table_cell),
        ],
        [
            Paragraph("Gate 4: Abstention Gate", style_table_cell),
            Paragraph("Refusal on missing unoffered branches", style_table_cell),
            Paragraph("<b>PASSED in RAG pipeline</b>", style_table_cell),
            Paragraph("Production Ready", style_table_cell),
        ],
        [
            Paragraph("Gate 5: LoRA Publishing", style_table_cell),
            Paragraph("Publish verified adapter to Hugging Face", style_table_cell),
            Paragraph("<b>PREPARED (Private Hub)</b>", style_table_cell),
            Paragraph("Hold upload until GPU run", style_table_cell),
        ],
    ]
    table_gates = Table(gates, colWidths=[105, 155, 125, 130])
    table_gates.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
            ]
        )
    )
    story.append(table_gates)

    story.append(Spacer(1, 14))
    story.append(Paragraph("12. Scope of Claims, Evidence Limitations & Final Conclusions", style_h1))
    story.append(
        Paragraph(
            "<b>Audit Disclosures:</b><br/>"
            "1. <i>Execution Environment:</i> Active PyTorch in the host virtual environment is CPU-only (`2.14.1+cpu`). "
            "Although the machine possesses an NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM), GPU QLoRA fine-tuning was held "
            "pending installation of CUDA-enabled PyTorch (`cu121`).<br/>"
            "2. <i>Benchmark Data Provenance:</i> All scores, verbatim answers, and latency metrics are strictly anchored "
            "to the actual recorded benchmark data in <code>model_artifacts/five_level_test_results.json</code>.<br/>"
            "3. <i>Final Verdict:</i> The standalone LLM demonstrates impressive fluency and domain awareness but cannot be "
            "relied upon for unmediated mathematical decisions. Integrating the model within AI-CON's deterministic 4-tier "
            "architecture resolves 100% of the critical mathematical and geographical vulnerabilities.",
            style_body,
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("13. Appendix A: Benchmark Configuration & Runtime Specs", style_h1))
    
    app_a_data = [
        [Paragraph("<b>Configuration Parameter</b>", style_table_header), Paragraph("<b>Specification / Environment Value</b>", style_table_header)],
        [Paragraph("Host Operating System", style_table_cell_bold), Paragraph("Windows 11 Enterprise (Build 10.0.26100)", style_table_cell)],
        [Paragraph("Hardware Platform", style_table_cell_bold), Paragraph("NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM) / Multithreaded Host CPU", style_table_cell)],
        [Paragraph("Python Environment", style_table_cell_bold), Paragraph("Python 3.10.11 Virtual Environment (<code>model_rag_agent_plan/.venv</code>)", style_table_cell)],
        [Paragraph("LLM Serving Backend", style_table_cell_bold), Paragraph("Ollama REST Engine (<code>http://localhost:11434</code>)", style_table_cell)],
        [Paragraph("AI-CON Model Details", style_table_cell_bold), Paragraph("<code>qwen2.5-aicon:latest</code> (Qwen2 3B, Q5_K_M GGUF, 36 layers, 2048 dim)", style_table_cell)],
        [Paragraph("Reference Model Details", style_table_cell_bold), Paragraph("<code>qwen2.5:7b</code> (Qwen2 7B, Q4_K_M GGUF, 28 layers, 3584 dim)", style_table_cell)],
        [Paragraph("Decoding Parameters", style_table_cell_bold), Paragraph("<code>temperature = 0.0</code> (deterministic greedy), <code>seed = 42</code>, <code>top_p = 1.0</code>", style_table_cell)],
        [Paragraph("Benchmark Execution File", style_table_cell_bold), Paragraph("<code>scripts/run_5_level_test.py</code>", style_table_cell)],
        [Paragraph("Test Results Artifact", style_table_cell_bold), Paragraph("<code>model_artifacts/five_level_test_results.json</code> (43,622 bytes)", style_table_cell)],
    ]
    tab_app_a = Table(app_a_data, colWidths=[165, 350])
    tab_app_a.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SECONDARY),
        ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
    ]))
    story.append(tab_app_a)

    story.append(Spacer(1, 12))
    story.append(Paragraph("14. Appendix B: Raw Evaluation Notes & Verification Data", style_h1))
    
    app_b_data = [
        [Paragraph("<b>Verification Target</b>", style_table_header), Paragraph("<b>Official Reference / Ground Truth Authority</b>", style_table_header), Paragraph("<b>Verification Status</b>", style_table_header)],
        [Paragraph("CAP Authority & Rules", style_table_cell), Paragraph("State Common Entrance Test Cell, Maharashtra - Info Brochure 2024-25", style_table_cell), Paragraph("Verified (Sole statutory body)", style_table_cell)],
        [Paragraph("Option Form Choices", style_table_cell), Paragraph("CET Cell Rule 9(1) - Candidates may enter up to 300 choice codes", style_table_cell), Paragraph("Verified (Not 5 or 15)", style_table_cell)],
        [Paragraph("Cutoff Database Scale", style_table_cell), Paragraph("181,137 official CAP cutoff records across 2023-24 and 2024-25", style_table_cell), Paragraph("Verified in SQLite/Parquet DB", style_table_cell)],
        [Paragraph("College Profile Directory", style_table_cell), Paragraph("1,041 participating engineering institutions across 36 districts", style_table_cell), Paragraph("Verified in ChromaDB vector store", style_table_cell)],
        [Paragraph("Tabular Model Accuracy", style_table_cell), Paragraph("Closing Rank R² = 0.5808, Percentile R² = 0.5401 on 15k test split", style_table_cell), Paragraph("Verified in model_artifacts/", style_table_cell)],
        [Paragraph("SRCEM College Location", style_table_cell), Paragraph("Shri Ramdeobaba College is situated in Nagpur (not Pune)", style_table_cell), Paragraph("Verified (DTE Code: 4115)", style_table_cell)],
    ]
    tab_app_b = Table(app_b_data, colWidths=[130, 265, 120])
    tab_app_b.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
    ]))
    story.append(tab_app_b)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully compiled PDF report to: {pdf_path}")


def package_deliverables(base_dir: Path):
    """Zip all deliverables into AI_CON_Evaluation_Report.zip."""
    zip_path = base_dir / "AI_CON_Evaluation_Report.zip"
    files_to_zip = [
        "AI_CON_Model_Evaluation_Report.pdf",
        "AI_CON_Model_Evaluation_Report.md",
        "generate_report.py",
        "README.md",
    ]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in files_to_zip:
            fpath = base_dir / fname
            if fpath.is_file():
                zf.write(fpath, arcname=fname)
                print(f"  Added to archive: {fname}")
    print(f"Deliverables successfully packaged to: {zip_path} ({zip_path.stat().st_size:,} bytes)")


def main():
    print("=" * 80)
    print("GENERATING AI-CON TECHNICAL MODEL EVALUATION REPORT")
    print("=" * 80)

    script_dir = Path(__file__).resolve().parent
    # Check if run from workspace or inside AI_CON_Evaluation_Report
    if script_dir.name == "AI_CON_Evaluation_Report":
        out_dir = script_dir
        root_dir = script_dir.parent
    else:
        out_dir = script_dir / "AI_CON_Evaluation_Report"
        root_dir = script_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = root_dir / "model_artifacts" / "five_level_test_results.json"
    if not json_path.is_file():
        # Fallback path check
        json_path = Path("model_artifacts/five_level_test_results.json").resolve()

    print(f"Loading benchmark source: {json_path}")
    data = load_test_results(json_path)
    print(f"Loaded {len(data)} evaluated question benchmarks.")

    pdf_path = out_dir / "AI_CON_Model_Evaluation_Report.pdf"
    md_path = out_dir / "AI_CON_Model_Evaluation_Report.md"
    readme_path = out_dir / "README.md"

    # 1. Build Markdown Report
    print("Generating Markdown report...")
    build_markdown_report(data, md_path)

    # 2. Build PDF Report
    print("Compiling PDF report with ReportLab...")
    build_pdf_report(data, pdf_path)

    # 3. Create README.md
    readme_content = f"""# AI-CON Model Evaluation Report Deliverables
**Benchmark:** 5-Level MHT-CET Engineering Admissions Counselling  
**Models:** AI-CON (`qwen2.5-aicon:latest`) vs. Reference (`qwen2.5:7b`)  
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  

## Package Contents
- `AI_CON_Model_Evaluation_Report.pdf`: Comprehensive ~20-page technical PDF report.
- `AI_CON_Model_Evaluation_Report.md`: Markdown version of the full technical report.
- `generate_report.py`: Standalone Python script to regenerate the PDF and Markdown reports.
- `README.md`: This inventory and instructions file.
- `AI_CON_Evaluation_Report.zip`: Standalone zip archive of all deliverables.

## How to Regenerate
```powershell
python generate_report.py
```
"""
    readme_path.write_text(readme_content, encoding="utf-8")
    print(f"Created package README at: {readme_path}")

    # 4. Package Zip Archive
    print("Creating ZIP package...")
    package_deliverables(out_dir)

    print("\nAll deliverables generated successfully!")


if __name__ == "__main__":
    main()
