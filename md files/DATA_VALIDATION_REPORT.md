# AI-CON Data Validation & Preparation Report

**Validation Execution Date:** October 15, 2026  
**Status:** ALL GATES PASSED (100% Valid, Zero Data Loss)  
**Primary Datasets Inspected:**
1. Multi-Year Hierarchical Cutoff Store (`cutoffs/phase3_final_staging/`)
2. Master Qualitative Institutional Profiles (`cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs/`)
3. Flat Historical Cutoff Archive (`cutoffs/raw_extracted/V4_daataa/training/all_records.csv`)
4. Generated Conversational SFT Splits (`training_data/train.jsonl`, `val.jsonl`)
5. Generated Tabular Prediction Dataset (`training_data/cutoff_tabular_features.csv`)

---

## 1. Cutoff Staging Data Validation Summary

Validation performed via `scripts/validate_cutoffs.py --cutoffs-dir cutoffs/phase3_final_staging`:

| Metric | Measured Value | Standard / Requirement | Status |
|---|---|---|---|
| **Files Inspected** | 2,013 JSON files | Must match all staging records | PASSED |
| **Valid Syntax Count** | 2,013 (100.0%) | 100% valid JSON syntax | PASSED |
| **Invalid Files** | 0 | 0 corrupted files allowed | PASSED |
| **Total Cutoff Observations** | 181,137 | Across 6 academic cycles | PASSED |
| **Accepted Observations** | 181,137 (100.0%) | Zero silent drops | PASSED |
| **Rejected Observations** | 0 (0.0%) | Zero unhandled records | PASSED |
| **Genuine Duplicates** | 0 | Unique (year, institute, branch, category, round, stage) | PASSED |
| **Contradictory Conflicts** | 0 | No conflicting ranks for same evidence ID | PASSED |
| **Critical Errors** | 0 | Zero blocking errors | PASSED |

### Breakdown by Academic Year (Cutoff Entries)
- **2020-21:** 17,856 cutoff entries
- **2021-22:** 19,247 cutoff entries
- **2022-23:** 27,611 cutoff entries
- **2023-24:** 34,159 cutoff entries
- **2024-25:** 37,206 cutoff entries
- **2025-26:** 45,058 cutoff entries
- **Total:** **181,137 entries**

---

## 2. Institutional Qualitative Profiles Validation

Validation performed via `scripts/validate_dataset.py`:

| Check | Result | Compliance Note |
|---|---|---|
| **Total JSON Profiles** | 1,041 files | Verified against `college_dataset_index.csv` |
| **Syntax Validity** | 1,041 (100.0%) | Strict JSON specification compliant |
| **Unique Record IDs** | 1,041 | IDs from `MHHEI_00001` to `MHHEI_01041` |
| **Duplicate IDs** | 0 | Zero duplicate keys |
| **Records with CET Code** | 378 (36.3%) | Verified engineering / technology colleges |
| **DHE Records without Code** | 663 (63.7%) | Legitimate non-CET colleges (Arts/Commerce/DHE) |
| **Affiliation Verified** | 126 (12.1%) | Sant Gadge Baba, SPPU, Mumbai Univ, BATU, etc. |
| **District Verified** | 378 (36.3%) | Clean district naming (Pune, Amravati, Mumbai, etc.) |
| **State Verified** | 1,041 (100.0%) | All confirmed in Maharashtra |
| **Ownership Status** | 1,040 (99.9%) | Government, Autonomous, Un-Aided, Private |
| **Manifest Checksum** | Passed (True) | Exact match with `dataset_manifest.json` |
| **Critical Errors** | **0** | Clean pass |

---

## 3. Training Dataset Generation & Distribution

The generation pipeline (`scripts/convert_to_training_data.py`) was executed with reproducible seed 42 to produce balanced conversational SFT examples:

### 3.1. Generated SFT Conversational Splits (`training_data/`)
- **Total Generated Examples:** **12,041**
  - **Grounded Cutoff Examples:** 10,000 (83.05%)
    - Cites exact `[evidence_id]`
    - Explicitly separates merit rank (int) and percentile (float)
    - Includes non-guarantee disclaimer
  - **Structured Abstention Examples:** 1,000 (8.30%)
    - Returns JSON structured refusal: `{"status": "insufficient_evidence", ...}`
    - Prevents hallucination when asked about unoffered categories/branches
  - **Verified College Info Examples:** 1,041 (8.65%)
    - Provides official affiliation, ownership, location, and type
    - Preserves source attribution and surfaces any conflicting records
- **Dataset Partitioning:**
  - **Train Split (`train.jsonl`):** **10,836 examples** (90.0%)
  - **Validation Split (`val.jsonl`):** **1,205 examples** (10.0%)
  - **Sample Smoke Dataset (`sample_sft.jsonl`):** **1,161 examples**

### 3.2. Tabular Prediction Dataset (`cutoff_tabular_features.csv`)
- **Total Records:** **116,744**
- **Accepted Valid Records:** 116,744 (100.0%)
- **Rejected Records:** 0 (0.0%)
- **Missing / Out-of-Range Percentiles:** 0
- **Columns (24):** `academic_year`, `institute_code`, `institute_name`, `course_code`, `course_name`, `seat_type`, `cap_round`, `stage`, `closing_rank`, `closing_percentile`, `list_type`, `branch_family`, `exam`, `evidence_id`, etc.

---

## 4. Training Loader & Tokenization Verification

The generated conversational splits were verified using Hugging Face `datasets.load_dataset("json", ...)`:
- `train.jsonl` loaded in 0.06s (177,575 examples/sec).
- `val.jsonl` loaded in 0.01s (117,546 examples/sec).
- Verified schema: Each row contains a `messages` array of length 3:
  1. `system` (anti-hallucination instruction)
  2. `user` (`EVIDENCE:\n...` + `QUESTION:\n...`)
  3. `assistant` (cited response or structured refusal)
- Zero malformed rows, zero empty lines, zero serialization errors.
