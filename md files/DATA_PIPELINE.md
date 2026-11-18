# AI-CON Data Pipeline Architecture & Mapping

**Document Version:** 1.0.0  
**Domain:** Maharashtra State Common Entrance Test Cell (MHT-CET CAP Engineering Admissions)  
**Target Systems:** Generative LLM Behavioural SFT (Task A) & Tabular Cutoff Regression (Task B)  

---

## 1. End-to-End Pipeline Overview

The AI-con data pipeline processes official State CET Cell centralized admission cutoff documents and institutional profiles through four distinct transformation tiers into verified, machine-readable training and retrieval assets:

```
[Raw CET Cell CAP PDFs]
       │
       ▼ (extract_data_v4.py / extract_historical_cutoffs.py)
[Raw Extracted JSONs] (cutoffs/raw_extracted/V4_daataa/<year>/)
       │
       ▼ (adapt_cutoff_data.py & reconcile_staging.py)
[Canonical Hierarchical Staging] (cutoffs/phase3_final_staging/<year>/<institute_code>.json)
       │
       ├───► [Vector Store] (ChromaDB collection 'college_info' via build_vector_index.py)
       │
       ├───► [Task A: Behavioural SFT JSONL] (training_data/sft_training_final.jsonl via convert_to_training_data.py)
       │       └── Messages Chat Format: system, user (EVIDENCE + QUESTION), assistant (CITATION + DISCLAIMER)
       │
       └───► [Task B: Tabular Regression CSV] (training_data/cutoff_tabular_features.csv)
               └── Features: Institute, Branch, Seat Type, Round, Stage -> Target: Closing Rank & Percentile
```

---

## 2. Source Data Specifications

### 2.1. Level 1: Raw Official Cutoff PDF Reports
The government publishes two distinct table formats across CAP rounds:
1. **Format B (Maharashtra State Seats / Minority Quota):**
   - Tables divided by university quota: Home University (HU), Other Than Home University (OHU), and State Level (SL).
   - Columns represent reserved categories: `GOPENS`, `GSCS`, `GSTS`, `GVJS`, `GNT1S`, `GNT2S`, `GNT3S`, `GOBCS`, `LOPENS`, `TFWS`, `EWS`, `PWDOPENS`, `DEFOPENS`.
   - Cell contents provide pairs of **Closing Merit Rank** and `(Closing Percentile)`.
2. **Format A (All India Quota Seats):**
   - Flat rows capturing All India merit numbers, choice codes, course names, and exam scores (JEE Main / MHT-CET).

### 2.2. Level 2: Raw Extracted JSON Files (`cutoffs/raw_extracted/V4_daataa/`)
Extracted programmatically using `pdfplumber` and regular expressions.
- Grouped by academic year folders: `2023-24/`, `2024-25/`, `2025-26/`.
- 332 raw college JSON files per academic cycle.
- Contains extraction report (`extraction_report.json`) and quarantine log (`quarantine.jsonl`) for unparsable text blocks.

### 2.3. Level 3: Canonical Staging (`cutoffs/phase3_final_staging/`)
Canonical multi-year repository structured by academic year (`2020-21` through `2025-26`):
- 2,013 individual JSON files named by 5-digit institute code (`<institute_code>.json`).
- Schema adheres to `model_rag_agent_plan/cutoffs/schema.json` (Draft 2020-12):
  - Normalized 5-digit institution codes (`"1002"` -> `"01002"`).
  - Explicit evidence IDs for every entry: `[YYYY-YY:INSTITUTE:COURSE:LEVEL:CATEGORY:ROUND:STAGE]`.
  - Disjoint list types: `"CAP"` or `"All India"`.
  - Rigorous numeric separation: Rank is an integer; Percentile is an independent float.

### 2.4. Level 4: Qualitative College Profiles (`cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs/`)
- 1,041 JSON files containing verified institutional data:
  - `institute_code`, `institute_name`, `official_website`, `institution_type`.
  - `extracted.identity`: `affiliation`, `ownership`, `district`, `state`.
  - Provenance: `sources_consulted` URLs and verification stamps (`verified_government`, `provided_master_list`).
  - Strict rule: Cutoff data is intentionally excluded to guarantee separation of concerns.

---

## 3. Data Transformation & Conversion Scripts

The pipeline provides specific scripts for each stage:

| Script | Input Path | Output Path | Purpose |
|---|---|---|---|
| `validate_cutoffs.py` | `cutoffs/phase3_final_staging` | Audit Log / Console | Audits schema validity, detects duplicate evidence IDs, and validates numeric ranges |
| `validate_dataset.py` | `cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs` | `reports/validation_report.json` | Validates 1,041 college profiles, identity fields, and index consistency |
| `build_vector_index.py` | `cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs` | `./vector_index/` (ChromaDB) | Generates embeddings using `all-MiniLM-L6-v2` and creates persistent vector collection |
| `convert_to_training_data.py` | `cutoffs/phase3_final_staging` + College Info | `training_data/sft_training_final.jsonl` | Generates behavioural SFT chat-format examples (grounded cutoffs, abstentions, college info) |
| `train_model.py` | `training_data/` | `model_artifacts/` | Trains tabular predictor (Task B) and configures LLM behavioural pipeline (Task A) |
| `rag_pipeline.py` | `./vector_index` + `cutoffs/phase3_final_staging` | Structured Response / LLM Answer | End-to-end question routing, evidence retrieval, and grounded inference |

---

## 4. Expected Model Training Schemas

### 4.1. Task A: Behavioural LLM Fine-Tuning Schema (Conversational JSONL)
Format: OpenAI / Unsloth / Hugging Face TRL `SFTTrainer` compatible format. Each line in `sft_training_final.jsonl` is a JSON object:

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are an admission decision-support assistant for Maharashtra engineering colleges. Use only the supplied evidence. Cite evidence IDs in [brackets]. Never promise admission. A historical cutoff describes a past round's outcome, not a guarantee for any future round or year. If evidence is missing, respond with status=insufficient_evidence and say exactly what is missing."
    },
    {
      "role": "user",
      "content": "EVIDENCE:\n[2024-25:01002:0100219110:state_level:GOPENS:R1:S1] 2024-25 round 1 stage 1 (maharashtra_minority): closing rank 34240, percentile 88.5013511\n\nQUESTION: What were the GOPENS closing cutoffs for Civil Engineering at Government College of Engineering, Amravati in 2024-25?"
    },
    {
      "role": "assistant",
      "content": "Historical observation from the supplied records:\n- Round 1, stage 1: rank 34240, percentile 88.5013511 [2024-25:01002:0100219110:state_level:GOPENS:R1:S1]\nThis describes 2024-25 only - not a prediction or guarantee for any other year. Confirm against the official CET Cell notice before relying on it."
    }
  ]
}
```

#### Abstention / Missing Evidence Schema
When the queried category, round, or branch is not in the evidence, the assistant produces a structured refusal:
```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "EVIDENCE:\n[2024-25:01002:0100219110:state_level:GOPENS:R1:S1] ...\n\nQUESTION: What was the GSTS closing cutoff for Civil Engineering at Government College of Engineering, Amravati in 2024-25?"},
    {
      "role": "assistant",
      "content": "{\"status\": \"insufficient_evidence\", \"missing_information\": [\"GSTS record for Civil Engineering at Government College of Engineering, Amravati, 2024-25\"], \"next_action\": \"Check the official CET Cell cutoff list for this seat type, or confirm this category was offered at this college this year.\"}"
    }
  ]
}
```

### 4.2. Task B: Tabular Regression Dataset Schema (CSV)
Features used for predicting closing cutoffs:
- **Categorical Features:** `institute_code`, `course_code`, `branch_family`, `seat_type`, `list_type`, `academic_year`.
- **Numerical Features:** `cap_round`, `stage`.
- **Target Variables:**
  - `closing_rank` (Integer)
  - `closing_percentile` (Float)

---

## 5. Anti-Hallucination & Provenance Principles

1. **Facts Are Never Learned in LLM Weights:**
   Raw cutoff numbers and intake capacity fluctuate every season. All factual data is injected dynamically via exact retrieval into the user prompt.
2. **Every Metric Requires an Evidence ID:**
   Any statement containing a rank or percentile must cite its corresponding `[YYYY-YY:INSTITUTE:COURSE:LEVEL:CATEGORY:ROUND:STAGE]`.
3. **Metric Independence:**
   Merit rank (integer) and percentile (float) must never be conflated, averaged, or converted using arbitrary formulas.
4. **Mandatory Disclaimer:**
   Every generated output must include an explicit disclaimer noting that past cutoffs do not guarantee future admission.
