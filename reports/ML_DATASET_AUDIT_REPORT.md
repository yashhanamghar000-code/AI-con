# AI-CON ML Dataset Audit & Retraining Design Report (Task 12)

**Generated:** Audited on historical MHT-CET Cutoff Features Dataset  
**Target Dataset:** `C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons\repo_staging\training_data\cutoff_tabular_features.csv`  
**Total Records:** 116,744  

---

## 1. Dataset Overview & Partitioning
- **Total Records:** 116,744
- **Academic Years:**
  - 2023-24: 34,216 records
  - 2024-25: 37,308 records
  - 2025-26: 45,220 records
- **CAP Rounds:** Round 1: 78,962, Round 3: 16,869, Round 2: 16,060, Round 4: 4,853

---

## 2. Target Integrity & Low Percentile Verification
- **Closing Rank Bounds:** [13, 215,248]
- **Closing Percentile Bounds:** [0.00%, 100.00%]
- **Low Percentiles (< 5.0%ile):** 3,641 records.
  - *Audit Finding:* Verified legitimate. Low percentiles correspond to All-India merit allotments in DTE CAP reports where JEE Main scores are admitted into private/un-aided colleges.
- **Invalid Records:** 0 invalid ranks, 0 invalid percentiles.

---

## 3. Data Quality, Duplication & Contradictions
- **Duplicate Records on Key Tuple:** 3,804 rows.
- **Contradictory Groups:** 1,900 tuples where identical `(institute, course, seat_type, round, stage, year)` yielded divergent cutoffs.
  - *Root Cause:* Caused by collapsing sub-quota categories (Home University vs Other-than-Home University vs Minority).
- **Target Leakage:** Collinear columns identified: `all_india_merit_no`.

---

## 4. Chronological Holdout Baseline Comparison
A chronological validation was conducted:
- **Train Partition (2023-2025):** 71,524 samples
- **Unseen Holdout (2025-26):** 45,220 samples

| Metric | Simple Historical Median Baseline | Previous ML Model (Random Split) |
|---|---|---|
| **Percentile MAE** | **10.73%** | 15.04% |
| **Percentile RMSE** | **16.71%** | 19.22% |
| **Percentile R²** | **0.6289** | 0.5261 |
| **Rank MAE** | **22,999** | 28,348.8 |
| **Rank RMSE** | **33,302** | 35,719.5 |
| **Rank R²** | **0.6882** | 0.5713 |

> 💡 **Key Audit Finding:** A simple historical median lookup on the chronological holdout beats the naive random-split ML regressor by **+4.31 percentile points** and **+5,349 rank positions**.

---

## 5. Retraining Design Specifications
1. **Deduplication with Disambiguation:** Disambiguate multi-quota rows before training.
2. **Chronological Holdout:** Validate on 2025-26 holdout rather than random k-fold splitting.
3. **Artifact Safety:** Existing production artifacts in `model_artifacts/` remain intact. New models must be saved in versioned subdirectories (e.g. `model_artifacts/v2_candidate/`).
