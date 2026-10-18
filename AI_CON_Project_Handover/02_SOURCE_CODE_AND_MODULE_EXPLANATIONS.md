# AI-CON: Source Code & Module Technical Explanations

**Document ID:** AI-CON-CODE-02  
**Codebase Root:** `C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons\AI-cons\AI-cons\model_rag_agent_plan`  
**Python Runtime:** Python 3.10.11 Virtual Environment (`.venv`)  

---

## 1. Codebase Structure Overview

The codebase is organized into four logical subsystems:
1. **Agent Orchestration & Resolution (`scripts/agents/`)**: Multi-agent query routing, entity disambiguation, and structured evidence assembly.
2. **Data Pipeline & Ingestion (`scripts/`)**: PDF parsing, staging reconciliation, tabular feature engineering, and SFT format conversion.
3. **Training & Evaluation (`scripts/`)**: Tabular gradient-boosted regression, Hugging Face LoRA/QLoRA fine-tuning, and model evaluation suites.
4. **Automated Unit Testing (`tests/`)**: 111 unit tests validating deterministic rules, Chroma vector indexing, and pipeline invariants.

---

## 2. Core Agent Modules (`scripts/agents/`)

### 2.1 `orchestrator.py` (33,261 bytes)
- **Role**: Central nervous system of the conversational interface. Coordinates query routing between `CollegeResolver`, `CutoffAgent`, `CollegeInfoAgent`, and the LLM client.
- **Key Classes**:
  - `Orchestrator`: Initializes all agents, receives raw text queries, and outputs structured `OrchestratorResult`.
  - `OrchestratorResult`: Dataclass containing `status` (`'answered'`, `'needs_clarification'`, `'insufficient_evidence'`), `answer` text, and `evidence` citations.
- **Workflow**:
  1. Calls `CollegeResolver.resolve(query)` to identify colleges and extract institute codes.
  2. If ambiguous, returns candidates with a clarification request.
  3. Identifies intent (`'cutoff'`, `'info'`, `'recommendation'`).
  4. Collects deterministic evidence blocks with bracketed IDs.
  5. If LLM is available, passes evidence to `OllamaClient` for grounded synthesis; otherwise returns formatted evidence directly.

### 2.2 `college_resolver.py` (20,973 bytes)
- **Role**: Entity resolution and fuzzy matching for college names across Maharashtra.
- **Key Methods**:
  - `load_index(csv_path)`: Loads 1,041 verified institutions from `college_dataset_index.csv`.
  - `resolve(query)`: Uses exact substring, normalized token overlap, and Levenshtein similarity to match user inputs (e.g. *"COEP"*, *"VJTI"*, *"Pict Pune"*).
  - `is_ambiguous(matches)`: Flags queries matching multiple distinct campuses (e.g. *"Government College"*) to prevent false matches.

### 2.3 `cutoff_agent.py` (10,552 bytes)
- **Role**: Deterministic retrieval of official historical cutoff percentiles and closing ranks.
- **Key Methods**:
  - `query_cutoffs(institute_code, academic_year, branch, seat_type)`: Executes exact lookups across the 181,137 cutoff records.
  - `format_evidence_payload(...)`: Generates standardized bracketed citation blocks:
    ```text
    [2024-25:01002:0100219110:state_level:GOPENS:R1:S1] 2024-25 Government College of Engineering, Amravati - Civil Engineering - GOPENS: closing rank 34240, percentile 88.5013511
    ```

### 2.4 `college_info_agent.py` (6,496 bytes)
- **Role**: Qualitative institution search over verified college profiles using dense vector embeddings.
- **Key Methods**:
  - `query_info(institute_code or query_text)`: Queries ChromaDB collection (`vector_index/chroma.sqlite3`) for affiliation, district, autonomy, and website data.
  - `format_info_evidence(...)`: Formats profile metadata for citation in LLM responses.

---

## 3. Data Processing & Pipeline Scripts (`scripts/`)

| Script Name | File Size | Description & Key Functions |
|:---|:---:|:---|
| `adapt_cutoff_data.py` | 24,026 bytes | Standardizes legacy and new cutoff formats into canonical staging structures. |
| `admission_rules.py` | 12,357 bytes | Implements statutory Maharashtra reservation logic (Caste Validity, Non-Creamy Layer, HU/OHU/SL quotas). |
| `build_vector_index.py` | 10,690 bytes | Reads 1,041 JSON college profiles, generates text chunks, and embeds them into ChromaDB SQLite index. |
| `college_adapter.py` | 13,776 bytes | Bridges heterogeneous raw college directories into unified schema objects. |
| `convert_to_training_data.py` | 11,296 bytes | Converts staging cutoffs and college profiles into `cutoff_tabular_features.csv` (116,744 rows) and `sft_training_final.jsonl` (12,041 pairs). |
| `cutoff_analyzer.py` | 11,032 bytes | Analyzes multi-year cutoff trends, drift, and seat absorption rates across CAP rounds. |
| `extract_historical_cutoffs.py` | 18,075 bytes | Extracts tabular cutoff matrices from raw CET Cell PDF bulletins. |
| `ollama_client.py` | 4,362 bytes | Lightweight client for local Ollama REST API (`/api/generate` and `/api/chat`) with timeout and error handling. |
| `option_planner.py` | 6,644 bytes | Algorithms to construct 300-choice CAP option forms with safe, target, and reach tiers. |
| `rag_pipeline.py` | 6,499 bytes | End-to-end RAG harness combining ChromaDB semantic search with structured evidence. |
| `recommendation_engine.py` | 9,556 bytes | Heuristic and ML-based recommendation scoring based on candidate score, category, and commute preferences. |
| `reconcile_staging.py` | 17,272 bytes | Verifies staging file consistency across years, removing duplicate records and validating IDs. |
| `validate_cutoffs.py` | 26,933 bytes | Comprehensive cutoff data validation checking for missing rounds, negative ranks, or invalid percentiles. |
| `validate_dataset.py` | 18,318 bytes | Validates the final training dataset (`train.jsonl`, `val.jsonl`) for formatting, schema compliance, and leak prevention. |

---

## 4. Model Training & Evaluation Scripts (`scripts/`)

### 4.1 `train_model.py` (15,215 bytes)
- **Purpose**: Trains the tabular closing rank and percentile regressors.
- **Algorithm**: `HistGradientBoostingRegressor` from `sklearn.ensemble`.
- **Features Used**: `academic_year`, `institute_code`, `course_code`, `seat_type`, `candidature_type`, `cap_round`, `stage`.
- **Outputs**:
  - `model_artifacts/cutoff_regressor_rank.joblib`
  - `model_artifacts/cutoff_regressor_percentile.joblib`
  - `model_artifacts/label_encoders.joblib`
  - `model_artifacts/tabular_metrics.json`

### 4.2 `train_qwen_lora.py` (14,603 bytes)
- **Purpose**: Fine-tunes language models (Qwen 2.5 3B / TinyLlama) using LoRA / QLoRA on `sft_training_final.jsonl`.
- **Key Enhancements**:
  - Verified `AutoModelForCausalLM.from_pretrained()` loading (fixes random weight initialization bug).
  - CUDA GPU detection and automatic device mapping.
  - BitsAndBytes 4-bit quantization configuration (`BitsAndBytesConfig`).
  - PEFT `LoraConfig` targeting attention projections (`q_proj`, `k_proj`, `v_proj`, `o_proj`).
  - Artifact saving into `model_artifacts/qwen3b_lora_adapter/`.

### 4.3 `run_5_level_test.py` (7,358 bytes)
- **Purpose**: Executes the 5-Level progressive evaluation benchmark against local Ollama models.
- **Models Evaluated**: `qwen2.5-aicon:latest` vs. `qwen2.5:7b`.
- **Parameters**: Greedy decoding (`temperature=0.0`, `seed=42`).
- **Output**: Generates `model_artifacts/five_level_test_results.json` capturing verbatim model outputs and execution latencies.

### 4.4 `compare_models.py` (13,122 bytes) & `evaluate_model.py` (12,317 bytes)
- **Purpose**: Automated regression evaluation testing exact cutoff retrieval, qualitative profile extraction, ambiguity clarification, and anti-hallucination abstention.
- **Outputs**: Generates `model_artifacts/evaluation_report.json` and `model_artifacts/model_comparison_results.json`.

---

## 5. Root Project Scripts

- `build_college_list.py` (3,706 bytes): Rebuilds the master CSV directory of colleges from raw scraped profiles.
- `extract_data_v4.py` (35,690 bytes): High-throughput scraper and text parser converting official DTE/CET Cell college summary HTML/PDF pages into structured JSON profiles.

---

## 6. Unit Testing Suite (`tests/`)

The test suite contains **111 unit tests** executed via Python's standard `unittest` framework:

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

### Verified Test Breakdown:
- `test_college_resolver.py` (4,885 bytes): Tests alias matching, abbreviation resolution (COEP, VJTI, SPIT), and ambiguity handling.
- `test_college_adapter.py` (6,549 bytes): Tests schema validation across heterogeneous raw college JSON objects.
- `test_chroma_indexing.py` (5,498 bytes): Tests vector store insertion, similarity search, and temporary collection teardown.
- `test_orchestrator_pipeline.py` (7,047 bytes): End-to-end test of query routing and evidence formatting.
- `test_phase1a_college_info.py` (12,139 bytes): Tests profile retrieval and district/autonomy parsing.
- `test_phase2_llm_rag.py` (26,159 bytes): Tests LLM prompt construction, citation grounding, and mock client fallbacks.
- `test_phase3_admission_intelligence.py` (79,521 bytes): Comprehensive battery testing statutory reservation rules, TFWS quotas, and multi-round seat matrix absorption.
- `test_validation.py` (5,394 bytes): Tests dataset verification schemas.

**Test Execution Status:** 109 Passed, 2 Skipped (conditional on live GPU), 0 Failed.
