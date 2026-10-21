# AI-CON: End-to-End Execution & Setup Guide (Windows PowerShell)

This guide provides exact, tested Windows PowerShell commands to run the entire **AI-con** Maharashtra Engineering Admissions Counselling pipeline from scratch — from raw cutoff processing to model training, evaluation, and interactive question-answering.

---

## 1. Prerequisites & Environment Check

- **Operating System:** Windows 10 / 11 (64-bit)
- **Shell:** PowerShell 5.1 / PowerShell 7+
- **Python Version:** Python 3.11 (64-bit)
- **Hardware Acceleration:** Compatible with CPU and NVIDIA GPUs (RTX 4060 Laptop tested)
- **Local LLM Engine:** Ollama (Pre-installed at `C:\Users\<user>\AppData\Local\Programs\Ollama\ollama.exe`)

---

## 2. Fast Step-by-Step PowerShell Execution

Open PowerShell and navigate to the project directory:

```powershell
# Navigate to the core workspace directory
Set-Location -Path "C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons\AI-cons\AI-cons\model_rag_agent_plan"

# Verify Python version and virtual environment
.\.venv\Scripts\python.exe --version
```

### Step 1: Run Offline Regression & Unit Tests (111 Tests)
Verify that all resolvers, schemas, rules engines, analyzers, and adapters are functioning properly:
```powershell
.\.venv\Scripts\python.exe -m unittest discover tests -v
```
*Expected Result:* 111 tests ran, 109 passing, 2 skipped, 0 failures (`OK (skipped=2)`).

---

### Step 2: Validate Raw Datasets
Audit the 1,041 verified college qualitative profiles and 181,137 historical cutoff records:

```powershell
# 1. Validate the 1,041-college institutional profiles
.\.venv\Scripts\python.exe scripts/validate_dataset.py

# 2. Validate historical multi-year cutoffs (2020-21 through 2025-26)
.\.venv\Scripts\python.exe scripts/validate_cutoffs.py --cutoffs-dir cutoffs/phase3_final_staging
```
*Expected Result:*
- `TOTAL ERRORS: 0, TOTAL WARNINGS: 0` for college dataset.
- `VALIDATION RESULT: PASSED (All records valid, 181,137 entries accepted)` for cutoffs.

---

### Step 3: Build the Vector Database (ChromaDB)
Create persistent vector embeddings (`all-MiniLM-L6-v2`) over verified institutional profiles:

```powershell
# Build the persistent college vector index (all 1,041 colleges)
.\.venv\Scripts\python.exe scripts/build_vector_index.py --out ./vector_index --rebuild
```

---

### Step 4: Generate Training Datasets
Convert raw cutoff and college data into ML-ready formats:

```powershell
# 1. Generate Conversational Behavioural SFT Dataset (12,041 examples)
.\.venv\Scripts\python.exe scripts/convert_to_training_data.py `
  --cutoffs cutoffs/phase3_final_staging `
  --college-info cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs `
  --out training_data/sft_training_final.jsonl `
  --max-cutoff-examples 10000 `
  --abstention-examples 1000 `
  --seed 42

# 2. Split into Train (90%) and Validation (10%) sets
.\.venv\Scripts\python.exe -c @"
import json, random
from pathlib import Path
lines = [l for l in Path('training_data/sft_training_final.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
random.seed(42)
random.shuffle(lines)
split = int(len(lines) * 0.9)
Path('training_data/train.jsonl').write_text('\n'.join(lines[:split]) + '\n', encoding='utf-8')
Path('training_data/val.jsonl').write_text('\n'.join(lines[split:]) + '\n', encoding='utf-8')
print(f'Train split: {split}, Val split: {len(lines) - split}')
"@
```

---

### Step 5: Train Models & Save Artifacts

#### Task B: Train Tabular Cutoff Predictor (HistGradientBoosting)
Trains regression models on 116,744 cutoff records to predict closing ranks and closing percentiles:
```powershell
.\.venv\Scripts\python.exe scripts/train_model.py --task tabular
```
*Output Artifacts in `model_artifacts/`:*
- `cutoff_regressor_rank.joblib`
- `cutoff_regressor_percentile.joblib`
- `label_encoders.joblib`
- `tabular_metrics.json`

#### Task A: Train Generative LLM Behavioural LoRA Adapter
Fine-tunes LoRA adapter for grounded citations and anti-hallucination:
```powershell
# Fast smoke test / training run
.\.venv\Scripts\python.exe scripts/train_model.py --task lora --smoke-test
```
*Output Artifacts in `model_artifacts/lora_adapter/`:*
- `adapter_config.json`
- `adapter_model.safetensors`
- `training_metrics.json`

#### Local Offline LLM Setup (Ollama + GGUF)
Registers the local quantized model `qwen2.5-coder-3b-instruct-q5_k_m.gguf` as an Ollama model:
```powershell
# Register model with system prompt and hyperparameters
ollama create qwen2.5-aicon -f Modelfile.aicon
```

---

### Step 6: Evaluate Models & Counselling Behaviour
Execute the comprehensive evaluation suite covering both predictive accuracy and anti-hallucination gates:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_model.py
```
*Expected Result:*
- **Gate 1 (Tabular Predictor):** Test evaluation on 15,000 records (MAE, RMSE, R² for ranks & percentiles).
- **Gate 2 (Exact Cutoff Grounding):** 100% citation precision with exact evidence ID.
- **Gate 3 (Qualitative Profiles):** Grounded institutional facts retrieved from vector store.
- **Gate 4 (Abstention Gate):** Refuses to hallucinate missing categories, returning structured refusal.
- **Gate 5 (Ambiguity Gate):** Detects ambiguous college names and requests clarification.

---

### Step 7: Interactive Testing via CLI (`rag_pipeline.py`)

Test real queries against the trained pipeline:

#### 1. College Information Query (Vector RAG)
```powershell
.\.venv\Scripts\python.exe scripts/rag_pipeline.py `
  --vector-index ./vector_index `
  --question "What is the affiliation and autonomy of Government College of Engineering, Amravati?"
```

#### 2. Exact Cutoff Query with Grounded Ollama LLM
```powershell
.\.venv\Scripts\python.exe scripts/rag_pipeline.py `
  --cutoffs cutoffs/phase3_final_staging `
  --vector-index ./vector_index `
  --use-llm `
  --ollama-model qwen2.5-aicon:latest `
  --question "What was the GOPENS cutoff for Civil Engineering at Government College of Engineering, Amravati in 2024-25?"
```

#### 3. Missing Information Query (Testing Abstention)
```powershell
.\.venv\Scripts\python.exe scripts/rag_pipeline.py `
  --cutoffs cutoffs/phase3_final_staging `
  --vector-index ./vector_index `
  --question "What was the GSTS cutoff for Aerospace Engineering at Indala College in 2024-25?"
```
*(Returns `status: unavailable` or structured notice without guessing)*

---

## 3. Directory Layout of Saved Outputs

```
model_artifacts/
├── cutoff_regressor_rank.joblib          # Trained Gradient Boosting model for Closing Rank
├── cutoff_regressor_percentile.joblib    # Trained Gradient Boosting model for Closing Percentile
├── label_encoders.joblib                 # Categorical feature encoders (Institute, Course, Quota)
├── tabular_metrics.json                  # Test evaluation metrics (MAE, RMSE, R²)
├── evaluation_report.json                # End-to-end multi-gate validation results
└── lora_adapter/                         # Fine-tuned behavioural LoRA adapter
    ├── adapter_config.json               # PEFT adapter configuration
    ├── adapter_model.safetensors         # Adapter weights
    └── training_metrics.json             # Training loss and step statistics

training_data/
├── cutoff_tabular_features.csv           # Cleaned 116,744 tabular cutoff records
├── sft_training_final.jsonl              # 12,041 full conversational SFT examples
├── train.jsonl                           # 10,836 training split examples (90%)
├── val.jsonl                             # 1,205 validation split examples (10%)
└── sample_sft.jsonl                      # 1,161 sample subset examples
```
