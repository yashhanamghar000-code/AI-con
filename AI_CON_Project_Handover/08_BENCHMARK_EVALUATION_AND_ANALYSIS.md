# AI-CON: Benchmark Evaluation, Raw Traces & Scorecard

**Document ID:** AI-CON-EVAL-08  
**Benchmark Suite:** 5-Level Progressive MHT-CET Counselling Benchmark (`scripts/run_5_level_test.py`)  
**Artifact Source:** `model_artifacts/five_level_test_results.json` (43,604 bytes)  
**Comprehensive PDF Report:** [`AI_CON_Evaluation_Report/AI_CON_Model_Evaluation_Report.pdf`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI-cons/AI-cons/model_rag_agent_plan/AI_CON_Evaluation_Report/AI_CON_Model_Evaluation_Report.pdf) (22 Pages)  

---

## 1. Benchmark Objective & Protocol

The 5-Level benchmark is designed to evaluate local language models across increasing reasoning complexity in Maharashtra engineering admissions:
- **Level 1 (Easy)**: Basic procedural understanding of CAP admissions and option forms.
- **Level 2 (Moderate)**: Academic comparative analysis (CS vs IT vs AI&DS) with trend vs data demarcation.
- **Level 3 (Hard)**: Numerical cutoff comparisons across three colleges with missing dimensions.
- **Level 4 (Very Hard)**: Conflicting constraints (location, score, commute, reservation document ambiguity).
- **Level 5 (Extremely Hard)**: Severe multi-constraint synthesis with hard negative constraints.

### Test Configuration
- **Inference Server**: Local Ollama Engine (`http://localhost:11434`).
- **AI-CON Model**: `qwen2.5-aicon:latest` (Qwen2 3B, Q5_K_M GGUF).
- **Reference Model**: `qwen2.5:7b` (Qwen2 7B, Q4_K_M GGUF).
- **Decoding Parameters**: Greedy decoding (`temperature = 0.0`, `seed = 42`, `top_p = 1.0`).

---

## 2. Executive Scorecard & Comparison Table

Each question was scored out of 10 points using an official 5-dimension rubric:
- *Factual Correctness (0–3)*
- *Reasoning & Comparison (0–2)*
- *Completeness (0–2)*
- *Handling of Uncertainty (0–2)*
- *Clear Explanation (0–1)*

| Level | Question Description | AI-CON (`3B`) | Reference (`7B`) | Primary Factual Errors Identified | Missing Info Handling |
|:---|:---|:---:|:---:|:---|:---|
| **Q1** | Basic CAP Counselling | **4.5 / 10** | **6.0 / 10** | **AI-CON**: Cited "Maharashtra University" authority, claimed 5-preference limit.<br/>**Ref**: Claimed MSBTE conducts CAP, capped preferences at 15 colleges. | AI-CON asked for rank & seats.<br/>Ref asked for exact score & HSC marks. |
| **Q2** | Branch Trade-offs (CS/IT/AI) | **7.5 / 10** | **8.0 / 10** | **AI-CON**: Separated AI and DS degree nomenclature.<br/>**Ref**: Minor oversimplification of IT curriculum. | Both separated macro industry demand from institutional placement claims. |
| **Q3** | Cutoff Comparison (92.40%) | **5.0 / 10** | **7.0 / 10** | **AI-CON**: Critical inequality failure (`92.40 > 95`); invented mock cutoffs.<br/>**Ref**: Also invented mock cutoffs without evidence. | Both identified missing category, round, and quota dimensions. |
| **Q4** | Conflicting Constraints | **6.5 / 10** | **5.5 / 10** | **AI-CON**: Invented non-existent "MSET" university.<br/>**Ref**: **Critical Geographical Hallucination** (Ramdeobaba in Pune). | **AI-CON refused to assume reserved status**.<br/>Ref prematurely assigned quotas. |
| **Q5** | Multi-Constraint Synthesis | **6.0 / 10** | **6.5 / 10** | Both models violated negative constraint by generating fictitious College A/B/C cards with ₹1.2L–₹1.4L fees. | **AI-CON**: Outstanding conceptual separation of eligibility vs guarantee.<br/>Ref: Detailed audit process. |
| **TOTAL** | **All 5 Tiers** | **29.5 / 50 (59.0%)** | **33.0 / 50 (66.0%)** | Standalone generative LLMs cannot be trusted for unmediated arithmetic decisions. | Both models require architectural guardrails for zero-shot abstention. |

---

## 3. Question-by-Question Diagnostic Audit

### Q1: Easy, Basic Counselling (85 Percentile in MHT-CET)
- **Prompt**: Student scored 85 percentile in MHT-CET and wants a computer branch in Maharashtra. Explain CAP steps, college preferences, and missing information before recommending colleges.
- **Audited Findings**:
  - *Authority Error*: AI-CON cited "Maharashtra University"; Reference cited "MSBTE". Both are false. The statutory body is the **State Common Entrance Test Cell, Maharashtra**.
  - *Option Form Capacity Error*: AI-CON asserted preferences are ranked 1 to 5. Reference asserted a limit of 15 colleges. Both are false. Official CET Information Brochure Rule 9(1) allows **up to 300 choice codes**.
  - *Scrutiny Center Verification*: Reference stated verification occurs *after* college allotment. In reality, e-Scrutiny or physical Scrutiny Center verification occurs *before* merit list finalization.

### Q2: Moderate, Branch Comparison (CS vs IT vs AI&DS)
- **Prompt**: Compare Computer Engineering, Information Technology, and Artificial Intelligence & Data Science in curriculum, career opportunities, and factors to consider. Clearly distinguish macro industry trends from verified placement data.
- **Audited Findings**:
  - Both models accurately explained that CE focuses on hardware/systems, IT on software/networking, and AI&DS on machine learning/data pipelines.
  - Both models properly distinguished broad macroeconomic industry trends from the lack of primary audited college placement statistics.
  - AI-CON divided AI and Data Science into two standalone theoretical fields, whereas Maharashtra universities offer an integrated 4-year degree titled *Artificial Intelligence and Data Science*.

### Q3: Hard, Cutoff Comparison (The `92.40 < 95.00` Failure)
- **Prompt**: Student has 92.40 percentile in MHT-CET. Compare three colleges for Computer Engineering. Explain the difference between home university, other than home university, and state level cutoffs. Do not invent cutoffs.
- **Audited Findings**:
  - **CRITICAL ARITHMETIC INVERSION**: AI-CON produced the following line:
    > `- College B: You are eligible (92.40 > 95)`
    This is mathematically false ($92.40 < 95.00$). In real admissions, this error causes a student to waste a primary preference slot on an unattainable college.
  - *Root Cause*: Byte-pair tokenizers split `92.40` into subword fragments `['92', '.', '40']`. Autoregressive attention predicts lexical patterns (`You are eligible (<X> > <Y>)`) rather than executing floating-point arithmetic.
  - *Negative Constraint Violation*: Both models invented mock colleges (College A, B, C) with arbitrary cutoffs instead of strictly halting.

### Q4: Very Hard, Conflicting Constraints (Pune Commute & Reserved Category)
- **Prompt**: Student scored 88 percentile, wants Computer or IT in Pune, insists on living at home with daily commute, says they "belong to a reserved category but haven't received the certificate yet." What is the strategic counselling advice?
- **Audited Findings**:
  - **CRITICAL GEOGRAPHICAL HALLUCINATION**: The Reference model recommended *Shri Ramdeobaba College of Engineering and Management (SRCEM)* for a student demanding a short commute in Pune. SRCEM is in **Nagpur**—over **700 km east of Pune**!
  - **AI-CON Reservation Discipline**: AI-CON correctly and strictly refused to treat unverified category eligibility as established, demanding Caste Validity and Non-Creamy Layer documentation prior to seat matrix matching.

### Q5: Extremely Hard, Multi-Constraint Synthesis
- **Prompt**: Multi-constraint profile: 96.35 percentile, budget ₹1.5L/year, wants Autonomous only, within 50 km of Pune or Mumbai, TFWS vs General, and strict instruction: *"If you do not have verified cutoff records for a specific college, state INSUFFICIENT_EVIDENCE instead of guessing."*
- **Audited Findings**:
  - **AI-CON Conceptual Excellence**: AI-CON delivered a masterclass breakdown in Step 6, explicitly separating statutory eligibility from statistical likelihood and absolute admission guarantee.
  - **Negative Constraint Violation**: Both models failed the hard negative constraint by generating fictitious cards for College A, B, and C with arbitrary fees (₹1.2L to ₹1.4L). The models should have refused to generate a shortlist until domicile, category, and specific fee approvals were provided.

---

## 4. Error Taxonomy & Severity Levels

| Severity | Category | Example from Benchmark | Risk to Student |
|:---|:---|:---|:---|
| **CRITICAL** | Mathematical Inversion | AI-CON stating `92.40 > 95` makes student eligible. | Student applies for unreachable college and loses seat. |
| **CRITICAL** | Geographical Hallucination | Reference model placing Nagpur's SRCEM in central Pune. | Student chooses college with impossible 700 km daily commute. |
| **HIGH** | Regulatory Authority Fabrication | AI-CON inventing "MSET" and "Maharashtra University". | Student navigates to fraudulent or non-existent portals. |
| **HIGH** | False Option Limits | AI-CON stating preferences are capped at 5 (actual: 300). | Student severely under-utilizes CAP preference strategy. |
| **MEDIUM** | Mock Card Generation | Both models inventing College A (₹1.2L) when told to abstain. | User mistakes mock examples for real recommendations. |
| **LOW** | Minor Nomenclature Splits | AI-CON treating AI and Data Science as separate degrees. | Slight confusion regarding curriculum structure. |

---

## 5. Official Deliverables Archive

For complete verbatim transcripts of all 5 questions, execution latencies, ReportLab styling, and 22-page compilation:
- **PDF Report**: `AI_CON_Evaluation_Report/AI_CON_Model_Evaluation_Report.pdf`
- **Markdown Text**: `AI_CON_Evaluation_Report/AI_CON_Model_Evaluation_Report.md`
- **Standalone ZIP Deliverable**: `AI_CON_Evaluation_Report/AI_CON_Evaluation_Report.zip` (87,854 bytes)
