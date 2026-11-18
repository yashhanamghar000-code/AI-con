# AI-CON: Education Counselling Assistant (Phase 1 Foundation)

AI-con (AI Consultant for Education) is an evidence-grounded education counselling application initially focused on Maharashtra engineering admissions through MHT-CET CAP counselling.

Phase 1 establishes the **Data Engineering and Retrieval Foundation**:
- Strict anti-hallucination guarantees: factual college information is retrieved from verified records.
- Zero cutoff hallucination: cutoff queries are strictly routed to an exact structured interface. Because the historical cutoff dataset is not yet present, the system returns an explicit `unavailable` status and never estimates, approximates, or invents cutoffs.
- College name resolution: supports exact CET institute codes, record IDs, full names, normalized aliases, and detects ambiguous matches to prompt for clarification.
- Complete independence from external LLM API keys: the pipeline operates in **evidence-only** mode for Phase 1.

---

## 1. Architecture Overview

```
                          Student Question
                                 │
                                 ▼
                     ┌──────────────────────┐
                     │   CollegeResolver    │
                     │ (Code / Name / ID)   │
                     └──────────┬───────────┘
                                │
               Ambiguous? ──────┴────── Matched?
             (needs_clarification)      │
                                        ▼
                             ┌──────────────────────┐
                             │  classify_intent()   │
                             │   (cutoff / info)    │
                             └──────────┬───────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
        [Cutoff Question]                       [College Info Question]
                    │                                       │
                    ▼                                       ▼
          CutoffAgent (exact)                     CollegeInfoAgent
        (Hierarchical JSONs)                     (Chroma Vector DB)
                    │                                       │
         Cutoff Dataset Missing?                            │
                    │                                       │
         YES ───────┴──────── NO                            │
          │                    │                            │
          ▼                    ▼                            ▼
  status: unavailable    Exact Historical          Factual Passages
  (Never hallucinated)     Cutoff Evidence         + Source Citations
          │                    │                            │
          └────────────────────┼────────────────────────────┘
                               │
                               ▼
                       Structured Evidence
                     (Evidence-only output)
```

---

## 2. Workspace Folder Structure

```
AI-cons/
├── college_ai_consultant_sparse_enriched_v4_no_cutoffs/  # Original college dataset (1,041 JSON files, untouched)
│   ├── dataset_manifest.json                             # Dataset manifest (v4.0 sparse verified)
│   ├── college_dataset_index.csv                         # CSV index of all 1,041 colleges
│   └── ...                                               # MHHEI_00001 to MHHEI_01041
│
└── model_rag_agent_plan/                                 # Retrieval, LLM & Admission Intelligence Foundation
    ├── requirements.txt                                  # Minimal dependencies (chromadb, sentence-transformers)
    ├── README.md                                         # Project guide across Phases 1, 2, and 3
    ├── MODEL_AND_RAG_PLAN.md                             # Architectural specification
    ├── cutoffs/                                          # Historical MHT-CET CAP Cutoff Store (Phase 3)
    │   ├── schema.json                                   # Formal JSON Schema (Draft 2020-12)
    │   ├── manifest.json                                 # Cutoff manifest & source integrity records
    │   └── <academic_year>/                              # e.g., 2023-24, 2024-25, 2025-26
    │       └── <institute_code>.json                     # e.g., 01002.json
    ├── scripts/
    │   ├── college_adapter.py                            # Reusable data adapter (CollegeRecord, factual_value)
    │   ├── validate_dataset.py                           # College dataset validation module & report generator
    │   ├── build_vector_index.py                         # Chroma vector store indexer
    │   ├── rag_pipeline.py                               # Pipeline entry point (answer_question)
    │   ├── ollama_client.py                              # Local Ollama HTTP client (Qwen 2.5 7B, temperature 0.0)
    │   ├── validate_cutoffs.py                           # Cutoff dataset schema & integrity validator (Phase 3.1)
    │   ├── adapt_cutoff_data.py                          # Deterministic cutoff ingestion adapter (Phase 3.1)
    │   ├── admission_rules.py                            # Deterministic CAP rules engine (Phase 3.2)
    │   ├── cutoff_analyzer.py                            # Historical multi-year & round analyzer (Phase 3.3)
    │   ├── recommendation_engine.py                      # Transparent evaluation & comparison engine (Phase 3.4)
    │   ├── option_planner.py                             # Balanced CAP option-form preference planner (Phase 3.5)
    │   └── agents/
    │       ├── college_resolver.py                       # College name/code resolution with ambiguity detection
    │       ├── college_info_agent.py                     # Semantic retrieval over Chroma collection
    │       ├── cutoff_agent.py                           # Exact structured cutoff lookup
    │       └── orchestrator.py                           # Routing and orchestration logic
    └── tests/
        ├── __init__.py                                   # Test package marker
        ├── test_college_adapter.py                       # Unit tests: Adapter & extraction logic
        ├── test_college_resolver.py                      # Unit tests: Code & name resolution
        ├── test_validation.py                            # Unit tests: Dataset validation checks
        ├── test_orchestrator_pipeline.py                 # Unit tests: Orchestrator routing & fixtures
        ├── test_chroma_indexing.py                       # Integration tests: Vector indexing
        ├── test_phase1a_college_info.py                  # Baseline Phase 1A regression tests
        ├── test_phase2_llm_rag.py                        # Unit tests: Phase 2 Local LLM + RAG
        └── test_phase3_admission_intelligence.py         # Unit tests: Phase 3 Admission Intelligence (All modules)
```

---

## 3. Dataset Schema (Sparse v4 JSON)

Each record in `college_ai_consultant_sparse_enriched_v4_no_cutoffs/` contains:
- `record_id`: Unique identifier (e.g. `"MHHEI_00001"`).
- `institute_code`: Optional 4-5 digit CET code (e.g. `"01002"`). Not all colleges have CET codes (e.g. DHE arts/commerce colleges).
- `institute_name`: Canonical institution name.
- `official_website`: Valid URL or omitted.
- `institution_type`: Government Autonomous, Un-Aided, etc.
- `extracted.identity`:
  - `affiliation`: Nested structure. May contain `value` or only `confidence`/`source`.
  - `ownership`: Verified ownership status.
  - `district` / `city` / `state`: Real values when verified; omitted when only confidence metadata is present.
- `extracted.admissions.note`: Explicitly notes that cutoff data is maintained separately.
- `sources_consulted`: List of source URLs.

**Extraction Rule:** Metadata fields like `"confidence": "provided_master_list"` or `"source": "Maharashtra State CET Cell"` are provenance attributes and are NEVER treated as factual values.

---

## 4. Setup & Python Environment (Windows PowerShell)

### Recommended Python Version
- **Python 3.10, 3.11, or 3.12 (64-bit)** on Windows.

### Virtual Environment Setup
Open PowerShell and run from the workspace:

```powershell
# Navigate to the Python project directory
Set-Location -Path "C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan"

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1
```

### Dependency Installation
```powershell
# Option A: Standard installation (downloads PyTorch automatically)
pip install -r requirements.txt

# Option B: Lightweight CPU-only PyTorch (recommended on Windows if saving disk space)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

---

## 5. Step-by-Step Execution Guide

### Step 1: Run Automated Tests
All unit tests run using the standard Python library with zero external downloads:

```powershell
Set-Location -Path "C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan"

# Run all test suites
python -m unittest discover tests -v
```

*Expected Output:*
- Adapter, resolver, validation, and orchestrator unit tests pass.
- Chroma integration tests pass if `chromadb` is installed, or skip cleanly with a notice if `chromadb` is not yet installed.

---

### Step 2: Validate the College Dataset
Run the reusable dataset validation module across all 1,041 records:

```powershell
Set-Location -Path "C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan"

python scripts/validate_dataset.py `
  --dataset "../college_ai_consultant_sparse_enriched_v4_no_cutoffs" `
  --csv-index "../college_ai_consultant_sparse_enriched_v4_no_cutoffs/college_dataset_index.csv" `
  --manifest "../college_ai_consultant_sparse_enriched_v4_no_cutoffs/dataset_manifest.json" `
  --report-out "./reports/validation_report.json"
```

*Expected Output:*
- Summary of 1,041 valid JSON files inspected.
- 0 invalid JSON syntax errors.
- 1,041 unique record IDs.
- Breakdown of records with CET institute codes vs legitimate DHE colleges without CET codes.
- Report written to `reports/validation_report.json`.

---

### Step 3: Build a 20-Record Sample Vector Index
Before indexing all 1,041 colleges, build a 20-record sample index to verify embedding and persistent storage:

> [!NOTE]
> **Network Notice:** The first time `build_vector_index.py` runs with the default model (`sentence-transformers/all-MiniLM-L6-v2`), HuggingFace downloads the ~90MB model weights to your local cache (`~/.cache/huggingface/hub`). Subsequent runs use the local weights.

```powershell
Set-Location -Path "C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan"

python scripts/build_vector_index.py `
  --college-info "../college_ai_consultant_sparse_enriched_v4_no_cutoffs" `
  --out "./vector_index_sample" `
  --limit 20 `
  --rebuild
```

*Expected Output:*
```
Rebuilding index: clearing existing directory ./vector_index_sample...
Indexed 20 chunks from 20 colleges (0 skipped) into ./vector_index_sample
```

---

### Step 4: Ask College Information Questions (Sample Index)

#### Query A: Query by College Name
```powershell
Set-Location -Path "C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan"

python scripts/rag_pipeline.py `
  --vector-index "./vector_index_sample" `
  --question "What is the affiliation of Government College of Engineering, Amravati?"
```

*Expected Output:*
```json
{
  "matched_college": "Government College of Engineering, Amravati",
  "institute_code": "01002",
  "record_id": "MHHEI_00001",
  "intent": "info",
  "evidence": "[MHHEI_00001:MHHEI_00001_profile] (profile, source: https://www.gcoea.ac.in/):\nCollege: Government College of Engineering, Amravati\nrecord_id: MHHEI_00001\ninstitute_code: 01002\ninstitution_type: Government Autonomous\naffiliation: Sant Gadge Baba Amravati University\nownership: Government Autonomous\nstate: Maharashtra\nofficial_website: https://www.gcoea.ac.in/\nSources consulted: https://www.gcoea.ac.in/; https://fe2026.mahacet.org/StaticPages/frmInstituteSummary?InstituteCode=01002",
  "status": "evidence_only"
}
```

#### Query B: Query by CET Institute Code Directly
```powershell
python scripts/rag_pipeline.py `
  --vector-index "./vector_index_sample" `
  --question "Tell me about institute 01002"
```

*Expected Output:*
- Resolves to `Government College of Engineering, Amravati` via institute code `01002`.

#### Query C: Query for a College Without a CET Code
```powershell
python scripts/rag_pipeline.py `
  --vector-index "./vector_index_sample" `
  --question "Tell me about Shri Sant Gajanan Maharaj College of Engineering, Shegaon"
```

---

### Step 5: Test Cutoff Query Handling (No Cutoff Dataset)
Test asking a cutoff question when no cutoff folder is provided:

```powershell
python scripts/rag_pipeline.py `
  --vector-index "./vector_index_sample" `
  --question "What was the GOPENS closing cutoff for Computer Engineering at Government College of Engineering, Amravati in Round 1?"
```

*Expected Output:*
```json
{
  "status": "unavailable",
  "matched_college": "Government College of Engineering, Amravati",
  "institute_code": "01002",
  "record_id": "MHHEI_00001",
  "intent": "cutoff",
  "message": "Cutoff data is not available in this workspace. College-information retrieval does not include ranks, percentiles, or CAP round closing figures. No cutoff values were generated.",
  "evidence": "CUTOFF EVIDENCE:\nCutoff data is not available in this workspace. College-information retrieval does not include ranks, percentiles, or CAP round closing figures. No cutoff values were generated."
}
```

---

### Step 6: Test College Ambiguity Handling
Ask about a college name that matches multiple institutions:

```powershell
python scripts/rag_pipeline.py `
  --vector-index "./vector_index_sample" `
  --question "What is the fee and affiliation of Government College of Engineering?"
```

*Expected Output:*
```json
{
  "status": "needs_clarification",
  "message": "Multiple colleges match your query... Please specify the exact college name or institute code.",
  "candidates": [
    "Government College of Engineering, Amravati",
    "Government College of Engineering,Yavatmal"
  ]
}
```

---

### Step 7: Build the Full 1,041-Record Vector Index
Once the sample index is verified, build the complete index:

```powershell
Set-Location -Path "C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan"

python scripts/build_vector_index.py `
  --college-info "../college_ai_consultant_sparse_enriched_v4_no_cutoffs" `
  --out "./vector_index" `
  --rebuild
```

*Expected Output:*
- Indexes 1,041 colleges into `./vector_index`.
- Total chunks: >= 1,041.
- Skipped: 0.

---

## 6. Cutoff Data Interface Specification

The hierarchical cutoff dataset is deliberately excluded in Phase 1. When cutoff data is integrated in subsequent phases, `CutoffAgent` expects the following directory structure:

```
<cutoffs_dir>/
  2024-25/
    01002.json
    01101.json
  2025-26/
    01002.json
```

Each `<institute_code>.json` file must adhere to:
```json
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
```

When supplied, pass `--cutoffs <path>` to `scripts/rag_pipeline.py`.

---

## 7. Phase 2: Local LLM + RAG Integration (Ollama + Qwen 2.5 7B)

Phase 2 connects the local Ollama daemon (`qwen2.5:7b`, Q4_K_M) to the retrieval foundation:
- **Local Client (`scripts/ollama_client.py`):** Zero external HTTP dependencies, uses standard Python `urllib.request`. Connects strictly to `http://localhost:11434` at `temperature: 0.0`.
- **Grounded Anti-Hallucination Prompting:** Injects strict rules instructing the model to answer exclusively from retrieved evidence chunks, cite evidence IDs in `[brackets]`, and acknowledge missing information without inventing values.
- **Strict Guardrails:** Ambiguous queries (`needs_clarification`) and missing cutoff queries (`unavailable`) short-circuit before any LLM inference, preventing any potential hallucination of admission cutoffs or ranks.
- **Graceful Failure (`status: "llm_error"`):** Connection errors (daemon offline) or missing model errors are caught and surfaced cleanly without discarding the retrieved evidence.

### Running Phase 2 Retrieval with Local LLM (PowerShell)

Ensure your local Ollama daemon is running with `qwen2.5:7b` available:
```powershell
# Verify Ollama status and model
ollama list
```

Run a grounded question through the pipeline:
```powershell
Set-Location -Path "C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan"

python scripts/rag_pipeline.py `
  --vector-index "./vector_index" `
  --question "What is the affiliation and district of Government College of Engineering, Amravati?" `
  --use-llm
```

Query with explicit college hint:
```powershell
python scripts/rag_pipeline.py `
  --vector-index "./vector_index" `
  --college "01002" `
  --question "Tell me about this college" `
  --use-llm
```

---

## 8. Phase 3: Admission Intelligence (MHT-CET CAP)

Phase 3 introduces verified admission intelligence, historical cutoff analysis, deterministic CAP rules, and transparent option-form planning:

### Core Principles
1. **Metric Independence:** State General Merit Rank (integer) and Entrance Percentile (float up to 7 decimal places) are distinct metrics and are **never** mathematically merged or compared against each other.
2. **Comparability Guardrails:** Multi-year or multi-round comparisons require exact alignment on Institute Code, Branch, Quota Category token, List Type (`CAP` vs `All India`), and Allotment Stage (`Stage 1` vs `Stage 2`).
3. **Deterministic Eligibility Rules:** Implements versioned CAP rules (`StudentProfile`, `EligibilityResult`, `AdmissionRulesEngine`):
   - **Candidature Types:** Distinguishes Maharashtra State Candidature (Type A) from Outside Maharashtra State (OMS, eligible for All India `AI` seats only).
   - **Quota Scope:** Resolves Home University (`GOPENH`, `LOPENH`) vs Other than Home University (`GOPENO`, `LOPENO`) vs State Level (`GOPENS`, `LOPENS`).
   - **Reservation Verification:** Requires valid Caste Validity and Non-Creamy Layer certificates; cleanly falls back to `OPEN` if documents are missing, or flags `needs_verification` if unverified.
   - **Supernumerary Quotas:** Evaluates `TFWS` (statutory annual income limit <= Rs. 8 LPA) and `EWS` (10% state-level quota).
4. **Transparent Classification Tiers (Recommendation Engine):**
   - `Historically more attainable`: Student score comfortably exceeds past closing metric.
   - `Competitive`: Student score is close to historical closing metric.
   - `Reach`: Historical closing cutoff was noticeably higher than student score.
   - `Eligibility Unresolved`: Missing verification fields prevent conclusive eligibility check.
   - `Ineligible`: Student legally disqualifies for this quota.
   - `Insufficient evidence`: No matching historical records exist.
   - **Zero Fabricated Probabilities:** Never predicts pseudo-scientific percentages (e.g. "92% chance").
5. **Strategic Option-Form Planning:** Structures candidate preferences into a balanced sequence (`Reach` -> `Competitive` -> `Attainable`), alerts the candidate if safety anchors are missing, and ensures **zero silent omission** by logging unplaced or ineligible choices with complete explanations.

---

## 9. Phase 3 Historical Cutoff & Admission Intelligence Manual Workflow

Follow these manual PowerShell commands in sequence. **Do not proceed to a subsequent step if a previous step fails.**

> [!IMPORTANT]
> **Data Safety & Isolation:** The original college dataset (`college_ai_consultant_sparse_enriched_v4_no_cutoffs/`), Chroma vector index (`vector_index/`), source PDFs, and historical raw extractions are strictly immutable. All intermediate processing writes to isolated staging directories under `cutoffs/`. Canonical promotion occurs only after full validation.

---

### Step 1: Run Phase 3 Unit Tests
Verify that all core Phase 3 logic (validation, adaptation, rules engine, analyzer, recommendation engine, option planner, orchestrator) passes offline.

- **Working Directory:** `C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan`
- **Exact Command:**
  ```powershell
  python -m unittest tests/test_phase3_admission_intelligence.py -v
  ```
- **Changes Files:** No.
- **Expected Output:**
  ```text
  Ran 48 tests in X.XXs
  OK
  ```
- **What an Error Looks Like:**
  `FAILED (failures=X, errors=Y)` with traceback.
- **What to do if it fails:**
  Inspect the failing test method and traceback. Do not proceed to extraction until all tests pass.

---

### Step 2: Inspect the Seven Historical PDFs and Inventory
Inspect the physical source files and verify their confirmed academic-year and CAP round dispositions in `cutoffs/reports/historical_pdf_inventory.json`.

- **Working Directory:** `C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan`
- **Exact Command:**
  ```powershell
  Get-ChildItem "cutoffs/historical_pdf_input" | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
  Get-Content "cutoffs/reports/historical_pdf_inventory.json" | ConvertFrom-Json | Select-Object -ExpandProperty pdfs | Format-Table filename, academic_year, cap_round, format_type -AutoSize
  ```
- **Changes Files:** No.
- **Expected Output:**
  - 7 PDF files listed with byte sizes (~2.7MB – 3.3MB).
  - Explicit dispositions:
    - `round-1-mht-cet-2020-mh.pdf` -> `2020-21`, CAP Round 1
    - `2020ENGG_CAP2_CutOff.pdf` -> `2020-21`, CAP Round 2
    - `2021ENGG_CAP1_CutOff.pdf` -> `2021-22`, CAP Round 1
    - `2021ENGG_CAP2_CutOff.pdf` -> `2021-22`, CAP Round 2
    - `2022ENGG_CAP1_CutOff.pdf` -> `2022-23`, CAP Round 1
    - `2022ENGG_CAP2_CutOff.pdf` -> `2022-23`, CAP Round 2
    - `2022ENGG_CAP3_CutOff.pdf` -> `2022-23`, CAP Round 3
- **What an Error Looks Like:**
  `Cannot find path 'cutoffs/historical_pdf_input'`.
- **What to do if it fails:**
  Ensure the PDFs are placed in `cutoffs/historical_pdf_input/`.

---

### Step 3: Extract Historical PDFs into Raw Staging
Extract tabular cutoff data from the 7 PDFs using the deterministic extraction script.

- **Working Directory:** `C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan`
- **Exact Command:**
  ```powershell
  python scripts/extract_historical_cutoffs.py `
    --input "cutoffs/historical_pdf_input" `
    --out "cutoffs/historical_raw_staging" `
    --reports-dir "cutoffs/reports"
  ```
- **Changes Files:** Yes: creates `cutoffs/historical_raw_staging/<academic_year>/<institute_code>_<college_slug>.json` and writes `cutoffs/reports/historical_extraction_report.json`.
- **Expected Output:**
  ```text
  ======================================================================
  AI-CON PHASE 3: HISTORICAL CUTOFF PDF EXTRACTION
  Input:   cutoffs\historical_pdf_input
  Output:  cutoffs\historical_raw_staging
  ======================================================================
  Found 7 historical PDFs to extract.
  [1/7] Inspecting: 2020ENGG_CAP2_CutOff.pdf ...
      -> Year: 2020-21, Round: 2, Extracted: ... records.
  ...
  ======================================================================
  EXTRACTION COMPLETE
  ======================================================================
  ```
- **What an Error Looks Like:**
  `ERROR: 'pdfplumber' is required for historical PDF table extraction. Please install it using: pip install pdfplumber`.
- **What to do if it fails:**
  Ensure `pdfplumber` is installed in your Python environment (`pip install pdfplumber`), then re-run.

---

### Step 4: Adapt Historical Records into Adapted Staging
Run the deterministic schema adapter to normalize institute codes (e.g. `01002`), clean branch names, generate stable evidence IDs, and validate records against the college dataset index.

- **Working Directory:** `C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan`
- **Exact Command:**
  ```powershell
  # A. Dry-run audit
  python scripts/adapt_cutoff_data.py `
    --source "cutoffs/historical_raw_staging" `
    --college-index "../college_ai_consultant_sparse_enriched_v4_no_cutoffs/college_dataset_index.csv" `
    --dry-run

  # B. Full adaptation into historical adapted staging
  python scripts/adapt_cutoff_data.py `
    --source "cutoffs/historical_raw_staging" `
    --out "cutoffs/historical_adapted_staging" `
    --college-index "../college_ai_consultant_sparse_enriched_v4_no_cutoffs/college_dataset_index.csv" `
    --report-out "cutoffs/reports/historical_adaptation_report.json"
  ```
- **Changes Files:** Yes (Part B creates `cutoffs/historical_adapted_staging/<academic_year>/<institute_code>.json`).
- **Expected Output:**
  ```text
  ======================================================================
  AI-CON PHASE 3: DETERMINISTIC CUTOFF ADAPTATION
  ======================================================================
  Files Scanned:        ...
  Colleges Adapted:     ...
  Rejected Stubs:       0
  Total Cutoffs Kept:   ...
  ADAPTATION SUCCESSFUL (0 errors detected)
  ======================================================================
  ```
- **What an Error Looks Like:**
  `FileNotFoundError` or nonzero error count in output.
- **What to do if it fails:**
  Verify that `cutoffs/historical_raw_staging` contains JSON files from Step 3.

---

### Step 5: Prepare the Final Chronological Merged Staging Dataset
Reconcile and merge historical adapted data (`cutoffs/historical_adapted_staging`) and current adapted data (`cutoffs/adapted_staging`) into a single chronological staging dataset across all 6 academic years (`2020-21` through `2025-26`).

- **Working Directory:** `C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan`
- **Exact Command:**
  ```powershell
  python scripts/reconcile_staging.py `
    --historical-dir "cutoffs/historical_adapted_staging" `
    --current-dir "cutoffs/adapted_staging" `
    --out "cutoffs/phase3_final_staging" `
    --reports-dir "cutoffs/reports"
  ```
- **Changes Files:** Yes: writes merged canonical `<institute_code>.json` files under `cutoffs/phase3_final_staging/<academic_year>/` and generates merge/conflict reports.
- **Expected Output:**
  ```text
  ======================================================================
  AI-CON PHASE 3: MULTI-YEAR CUTOFF DATA RECONCILIATION
  Historical Source: cutoffs\historical_adapted_staging
  Current Source:    cutoffs\adapted_staging
  Target Staging:    cutoffs\phase3_final_staging
  ======================================================================
  Total Cutoffs Reconciled:       ...
  Exact Duplicates Collapsed:     ...
  Conflicts Requiring Review:     0
  Cutoff Breakdown by Academic Year:
    - 2020-21: ... cutoffs
    - 2021-22: ... cutoffs
    - 2022-23: ... cutoffs
    - 2023-24: 34,159 cutoffs
    - 2024-25: 37,206 cutoffs
    - 2025-26: 45,058 cutoffs
  Audit reports saved to: cutoffs/reports/
  ======================================================================
  RECONCILIATION COMPLETE
  ======================================================================
  ```
- **What an Error Looks Like:**
  Nonzero conflicts or missing source directory error.
- **What to do if it fails:**
  Inspect `cutoffs/reports/reconciliation_conflicts_report.json` for details on any conflicting entries.

---

### Step 6: Validate the Complete Staging Dataset
Run the strict cutoff validator with offline PDF verification against the complete merged staging dataset.

- **Working Directory:** `C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan`
- **Exact Command:**
  ```powershell
  python scripts/validate_cutoffs.py `
    --cutoffs-dir "cutoffs/phase3_final_staging" `
    --college-index "../college_ai_consultant_sparse_enriched_v4_no_cutoffs/college_dataset_index.csv" `
    --pdf-dir "cutoffs/historical_pdf_input" `
    --report-out "cutoffs/reports/final_validation_report.json"
  ```
- **Changes Files:** Yes: writes `cutoffs/reports/final_validation_report.json`.
- **Expected Output:**
  ```text
  ======================================================================
  AI-CON PHASE 3: CUTOFF DATA VALIDATION
  Target Directory: cutoffs\phase3_final_staging
  ======================================================================
  Files Inspected:        ...
  Valid College Files:    ...
  Invalid College Files:  0
  Accepted Cutoffs:       ...
  Rejected Cutoffs:       0
  Critical Errors:        0
  VALIDATION RESULT: PASSED (All records valid)
  ======================================================================
  ```
- **What an Error Looks Like:**
  `VALIDATION RESULT: FAILED (Errors detected)` with exit code 1.
- **What to do if it fails:**
  Inspect `cutoffs/reports/final_validation_report.json` errors array to locate invalid fields or corrupted files.

---

### Step 7: Run the Full Regression Test Suite
Run the complete unit and regression test suite across Phase 1, Phase 2, and Phase 3.

- **Working Directory:** `C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan`
- **Exact Command:**
  ```powershell
  python -m unittest discover -s tests -p "test_*.py" -v
  ```
- **Changes Files:** No.
- **Expected Output:**
  ```text
  Ran XX tests in X.XXs
  OK
  ```
- **What an Error Looks Like:**
  `FAILED (failures=X, errors=Y)`.
- **What to do if it fails:**
  Fix any broken regression test before testing live queries.

---

### Step 8: Run an Exact Historical Cutoff Lookup
Query an exact historical cutoff using the newly validated final staging dataset.

- **Working Directory:** `C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan`
- **Exact Command:**
  ```powershell
  python scripts/rag_pipeline.py `
    --cutoffs "cutoffs/phase3_final_staging" `
    --vector-index "vector_index" `
    --question "What was the GOPENS cutoff for Computer Science and Engineering at Government College of Engineering, Amravati in 2024-25?" `
    --use-llm
  ```
- **Changes Files:** No.
- **Expected Output:**
  Structured JSON response containing `status: "grounded"`, exact closing rank, closing percentile, and citation bracketed with exact evidence ID (e.g. `[EV-01002-...]`).
- **What an Error Looks Like:**
  `status: "hallucination_detected"` or `status: "refusal"`.
- **What to do if it fails:**
  Verify Ollama is running (`ollama list`) and `qwen2.5:7b` is loaded.

---

### Step 9: Run a Historical Trend Query
Query historical cutoff progression across multiple continuous academic years.

- **Working Directory:** `C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan`
- **Exact Command:**
  ```powershell
  python scripts/rag_pipeline.py `
    --cutoffs "cutoffs/phase3_final_staging" `
    --vector-index "vector_index" `
    --question "What is the historical cutoff trend for Computer Science and Engineering at Government College of Engineering, Amravati across past years?" `
    --use-llm
  ```
- **Changes Files:** No.
- **Expected Output:**
  Structured JSON response with `intent: "trend"`, chronological rank progression, percentile progression, year-to-year deltas, and official disclaimer that historical trends do not guarantee future admission.
- **What an Error Looks Like:**
  `intent: "info"` or failure to find branches.
- **What to do if it fails:**
  Check that the college name resolves cleanly via `CollegeResolver`.

---

### Step 10: Run a Missing-Cutoff Safety Query
Verify guardrail behavior when querying cutoffs for a college or branch with no cutoff records.

- **Working Directory:** `C:\Users\Yash Hanamghar.Nyai\Documents\AI-cons\model_rag_agent_plan`
- **Exact Command:**
  ```powershell
  python scripts/rag_pipeline.py `
    --cutoffs "cutoffs/phase3_final_staging" `
    --vector-index "vector_index" `
    --question "What is the cutoff for Aerospace Engineering at Government College of Engineering, Amravati?" `
    --use-llm
  ```
- **Changes Files:** No.
- **Expected Output:**
  `status: "refusal"` or `message: "Cutoff data is not available..."`. No hallucinated cutoff figures or fabricated numbers.
- **What an Error Looks Like:**
  Invented rank or percentile.
- **What to do if it fails:**
  Verify `CUTOFF_UNAVAILABLE` fallback logic in `scripts/agents/orchestrator.py`.

---

## 10. Known Limitations & Scope Boundaries (Phase 3)

1. **Non-Predictive Historical Evidence:** Past CAP cutoffs reflect previous applicant distributions and seat matrices. Historical cutoffs never constitute a legal guarantee of future admission.
2. **Document Verification Responsibility:** The Admission Rules Engine evaluates eligibility based on declared candidate status. Official physical or e-Scrutiny verification by State CET Cell remains authoritative.
3. **Separate Data Stores:** Cutoff data is stored strictly in `cutoffs/<academic_year>/<institute_code>.json` and is never mixed into the college profile dataset (`college_ai_consultant_sparse_enriched_v4_no_cutoffs/`).
4. **Offline Local Model:** Natural language explanations are powered by local `qwen2.5:7b` via Ollama at `temperature: 0.0` with strict evidence citations (`[EV-...]`).
5. **PDF Verification Scope:** Historical years 2020-21 through 2022-23 are verified against official source PDFs physically located in `cutoffs/historical_pdf_input/`. Years 2023-24 through 2025-26 retain references to official CET Cell PDF filenames while being marked `SOURCE_PDF_UNVERIFIED_OFFLINE` until physical PDF copies are added.
