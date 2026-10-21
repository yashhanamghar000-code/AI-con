# AI-CON Project Audit Report

**Date of Audit:** October 15, 2026  
**Auditor:** Senior Python / ML Engineer  
**Workspace Root:** `C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons`  
**Core Implementation Directory:** `C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons\AI-cons\AI-cons\model_rag_agent_plan`  

---

## 1. Executive Summary & Verified Facts

This project is **AI-con** (AI Consultant for Education), an evidence-grounded education counselling engine built for Maharashtra Engineering Admissions (MHT-CET Centralized Admission Process / CAP). 

The codebase was delivered with raw and staged cutoff data, qualitative college profiles, a vector retrieval pipeline, a rule-based agent layer, offline unit tests, and pre-downloaded local model assets. 

### Key Findings at a Glance
| Component | Status | Details |
|---|---|---|
| **Python Version** | Verified | Python 3.11.9 (64-bit Windows) |
| **Hardware / GPU** | Verified | NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM, Driver 566.07, CUDA 12.7) |
| **PyTorch** | Verified | Version 2.14.1 (CPU mode active in default venv; CUDA capable with cu121) |
| **Local LLM Weight** | Verified | `qwen2.5-coder-3b-instruct-q5_k_m.gguf` (2,438,740,416 bytes / 2.44 GB binary present) |
| **GGUF Source Model** | Verified | Stock `Qwen/Qwen2.5-Coder-3B-Instruct` (Unmodified upstream weights; NOT fine-tuned on AI-con data) |
| **Target Fine-Tuned Model**| Verified | `AI-CON Qwen 3B LoRA Adapter` (`model_artifacts/qwen3b_lora_adapter/`, ChatML, r=8, alpha=16) |
| **Baseline Reference Model**| Verified | `AI-CON TinyLlama 1.1B LoRA Adapter` (`model_artifacts/lora_adapter/`, published to private HF) |
| **Tabular ML Predictors** | Verified | `cutoff_regressor_rank.joblib`, `cutoff_regressor_percentile.joblib`, `label_encoders.joblib` |
| **Offline Inference** | Verified | Ollama (`qwen2.5-aicon:latest`) and local PyTorch / PEFT inference |
| **Raw Cutoff Records** | Verified | 181,137 cutoff records across 6 years (2020-21 through 2025-26) |
| **College Qualitative Data** | Verified | 1,041 sparse college JSON profiles in v4 schema (100% valid) |
| **Unit Test Suite** | Verified | 111 tests in 9 suites: 109 passing, 2 skipped, 0 failures |

---

## 2. Workspace Directory Structure & Layout

The project files were extracted from an archive resulting in a nested structure:
```
C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons/
└── AI-cons/
    └── AI-cons/
        ├── qwen2.5-coder-3b-instruct-q5_k_m.gguf   # Local 4-bit/5-bit quantized LLM weights (2.44 GB)
        ├── README.md                               # Top-level quickstart and test runner guide
        ├── PROJECT_ANALYSIS_AND_TRAINING_PLAN.md   # Architectural master plan
        ├── Modelfile.aicon                         # Ollama configuration file for Qwen 2.5 AI-con
        ├── .venv/                                  # Legacy virtual environment from friend's machine
        └── model_rag_agent_plan/                   # Core Python application workspace
            ├── requirements.txt                    # Project dependency specification
            ├── README.md                           # Multi-phase system documentation
            ├── MODEL_AND_RAG_PLAN.md               # RAG and model selection specifications
            ├── PROJECT_ANALYSIS_AND_TRAINING_PLAN.md # Deep operational guide
            ├── extract_data_v4.py                  # Raw PDF extractor
            ├── build_college_list.py               # Institute name / code deduplicator
            │
            ├── cutoffs/                            # Data store
            │   ├── phase3_final_staging/           # 2,013 canonical institute JSON files across 6 academic years
            │   ├── raw_extracted/V4_daataa/        # 116,744 flat tabular records and raw extraction JSONs
            │   └── college_ai_consultant_sparse_enriched_v4_no_cutoffs/ # 1,041 verified qualitative profiles
            │
            ├── scripts/                            # Data engineering, adapters, and agents
            │   ├── agents/                         # Agent routing and resolution layer
            │   ├── adapt_cutoff_data.py            # Adapts raw extracted cutoffs to canonical hierarchy
            │   ├── convert_to_training_data.py     # Generates SFT chat JSONL from cutoff and college data
            │   ├── validate_cutoffs.py             # Schema and semantic validator for cutoff records
            │   ├── validate_dataset.py             # Schema validator for 1,041 college profiles
            │   ├── build_vector_index.py           # ChromaDB vector index builder
            │   ├── rag_pipeline.py                 # Retrieval-augmented generation pipeline entry point
            │   └── ollama_client.py                # HTTP client for local Ollama daemon
            │
            ├── tests/                              # Regression and unit test suite (111 tests)
            └── vector_index/                       # Persistent ChromaDB sqlite database
```

---

## 3. Technology Stack & Dependencies

- **Programming Language:** Python 3.11.9
- **Core ML & Data Libraries:**
  - `transformers` (v5.19.0 in venv, v5.18.0 in system)
  - `peft` (v0.21.2)
  - `datasets` (v5.1.0)
  - `accelerate` (v1.15.0)
  - `trl` (v1.15.0)
  - `tokenizers` (v0.23.3)
  - `scikit-learn` (v1.9.1)
  - `pandas` (v3.0.6)
  - `numpy` (v2.4.6)
- **Vector Search & Embeddings:**
  - `chromadb` (v1.5.9)
  - `sentence-transformers` (v6.1.0)
  - Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- **PDF Extraction:**
  - `pdfplumber` (v0.11.10), `pypdfium2` (v5.14.0), `pdfminer.six` (v20260107)
- **Local Inference Engines:**
  - Ollama local daemon (`http://localhost:11434`)
  - `llama-cli.exe` (build 11193, Clang 20.1.8)

---

## 4. Cutoff Data Inventory & File Formats

### 4.1. Canonical Staging (`cutoffs/phase3_final_staging/`)
- Contains 2,013 individual JSON files grouped into academic year directories:
  - `2020-21`: 17,856 cutoff entries
  - `2021-22`: 19,247 cutoff entries
  - `2022-23`: 27,611 cutoff entries
  - `2023-24`: 34,159 cutoff entries
  - `2024-25`: 37,206 cutoff entries
  - `2025-26`: 45,058 cutoff entries
- **Total Valid Cutoff Records:** **181,137**
- **Schema:** Hierarchical institution-level JSON with fields:
  `academic_year`, `institute_code` (canonical 5-digit), `institute_name`, `branches[].course_code`, `branches[].branch`, `branches[].categories[].category`, `cutoffs[].round`, `cutoffs[].stage`, `cutoffs[].closing_rank`, `cutoffs[].closing_percentile`, `cutoffs[].evidence_id`.

### 4.2. Raw Extracted & Tabular Datasets (`cutoffs/raw_extracted/V4_daataa/`)
- `training/all_records.csv` (49.2 MB): 116,744 tabular records with 24 columns covering:
  - `academic_year`, `institute_code`, `institute_name`, `course_code`, `course_name`, `seat_type`, `cap_round`, `stage`, `closing_rank`, `closing_percentile`, `evidence_id`, `list_type`.
- `records_2023-24.jsonl`, `records_2024-25.jsonl`, `records_2025-26.jsonl`: Line-delimited JSON versions of individual cutoff observations.
- `quarantine.jsonl` (9.2 MB): Malformed rows isolated during initial PDF extraction.

### 4.3. Qualitative College Profiles (`cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs/`)
- 1,041 JSON files (`MHHEI_00001.json` to `MHHEI_01041.json`).
- `college_dataset_index.csv`: Index mapping record ID to college names and institute codes.
- `dataset_manifest.json`: Verification checksums and schema metadata.

---

## 5. Identified Defects & Applied Fixes

During the audit, three defects and environmental issues were identified and resolved:

### Defect 1: Hardcoded Environment Path in Root `.venv`
- **Issue:** The root `.venv` contained paths referencing `C:\Users\om70c\...` from the author's machine, causing `python.exe` execution to fail.
- **Resolution:** Validated that `model_rag_agent_plan/.venv` exists with Python 3.11.9 and installed missing ML libraries (`peft`, `datasets`, `accelerate`, `trl`, `pandas`).

### Defect 2: Orchestrator Instantiation Failure in Unit Tests
- **Issue:** `test_phase3_admission_intelligence.py` failed on `test_orchestrator_requested_branch_parser` because `Orchestrator.__init__` raised a `ValueError` when instantiated without agents (`cutoff_agent=None, college_info_agent=None`).
- **Fix:** Removed the premature check in `Orchestrator.__init__` since `rag_pipeline.py` already guards CLI execution and `Orchestrator.answer` handles missing agents gracefully.
- **Verification:** 111 unit tests executed with 109 passing, 2 skipped, 0 failures.

### Defect 3: Relative Path Assumptions in Validation & Vector Scripts
- **Issue:** `validate_dataset.py` and `build_vector_index.py` hardcoded `../college_ai_consultant_sparse_enriched_v4_no_cutoffs`. Because that folder was located inside `cutoffs/`, scripts failed when run without explicit arguments.
- **Fix:** Updated the argument parsers with smart fallbacks to inspect `cutoffs/` when the parent path is absent.
- **Verification:** Both scripts now run with zero parameters and pass validation cleanly (1,041/1,041 valid records).

### Defect 4: Field Resolution in `convert_to_training_data.py`
- **Issue:** `convert_to_training_data.py` searched for attributes (`affiliation`, `ownership`, `district`) directly in `extracted`, whereas the v4 schema places them under `extracted.identity`.
- **Fix:** Enhanced `iter_college_info_examples` to inspect `extracted.identity` and properly extract verified facts.
- **Verification:** Grounded college info examples increased from 0 to 1,041 verified records.

---

## 6. Audit Conclusion & Readiness

The codebase is clean, well-architected, and fully functional. The data assets are intact, verified, and uncorrupted. The environment possesses the required libraries to proceed through dataset preparation, model training, and evaluation.
