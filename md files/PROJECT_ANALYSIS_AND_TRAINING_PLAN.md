# AI-CON: End-to-End Project Analysis, Cutoff Data Conversion & Model Training Plan

**Document Version:** 1.0.0  
**Target Architecture:** Maharashtra Engineering Admissions Decision Support (MHT-CET CAP Counselling)  
**Workspace:** `AI-cons/AI-cons`  

---

## Executive Summary & Core Architectural Principle

This project (**AI-con**) is an evidence-grounded education counselling engine designed for Maharashtra engineering admissions through the official State Common Entrance Test Cell Centralized Admission Process (MHT-CET CAP).

### The Cardinal Rule: Train Behaviour, Never Facts
In counselling systems, hallucinated or stale cutoffs cause severe harm to students.
1. **Never train/fine-tune an LLM to memorize raw numbers**:
   - Ranks, percentiles, intake numbers, seat counts, and fees change every single academic year.
   - A model that memorizes numbers during training will hallucinate obsolete data with false confidence and cannot be corrected without a complete retrain.
2. **Use Hybrid Architecture**:
   - **Exact Cutoffs**: Handled by **deterministic structured lookup** (`CutoffAgent`) querying verified hierarchical JSON files. Zero LLM hallucination risk.
   - **College Qualitative Facts** (affiliation, autonomy, NAAC, placements, facilities): Handled by **vector search / RAG** (`CollegeInfoAgent` using ChromaDB + embeddings).
   - **Model Fine-Tuning**: Focuses **strictly on behavior**:
     - Citing evidence in brackets (e.g., `[2024-25:01002:0100219110:state_level:GOPENS:R1:S1]`).
     - **Abstaining** (`status: insufficient_evidence`) when queried facts are missing rather than guessing.
     - Surfacing conflicts cleanly instead of silently picking an unverified secondary figure.
     - Following strict disclaimers (counselling decision support only, never promising admission).

---

## 1. Complete Project Structure & File Inventory

Below is an exhaustive breakdown of all files, directories, and data assets in the workspace:

```
AI-cons/
└── AI-cons/
    ├── qwen2.5-coder-3b-instruct-q5_k_m.gguf       # Local 4-bit/5-bit quantized LLM weights (2.44 GB)
    ├── README.md                                   # Root quickstart and test runner guide
    └── model_rag_agent_plan/                       # Core python workspace for data, agents, RAG, and tests
        ├── README.md                               # Architectural guide across Phases 1, 2, and 3 (34 KB)
        ├── MODEL_AND_RAG_PLAN.md                   # Architectural spec on model selection and RAG design (11 KB)
        ├── requirements.txt                        # Python dependencies (chromadb, sentence-transformers, pdfplumber)
        ├── build_college_list.py                   # Deduplicates college names and codes across year folders
        ├── extract_data_v4.py                      # Production PDF extractor for CET Cell CAP PDFs
        │
        ├── cutoffs/                                # Historical & canonical cutoff storage
        │   ├── raw_extracted/                      # Raw extraction output from extract_data_v4.py
        │   │   └── V4_daataa/                      # Multi-year extracted raw dataset
        │   │       ├── 2023-24/                    # 332 raw college JSON files + _index.json
        │   │       ├── 2024-25/                    # 332 raw college JSON files + _index.json
        │   │       ├── 2025-26/                    # 332 raw college JSON files + _index.json
        │   │       ├── college_master.csv          # Master list of all colleges seen in cutoffs
        │   │       ├── college_master_enriched.csv # Master list enriched with SPPU & DTE directory data
        │   │       ├── college_master_final.csv    # Final reconciled college master directory
        │   │       ├── extraction_report.json      # Extraction metrics, audit statistics & warnings
        │   │       ├── quarantine.jsonl            # Rows that could not be placed due to malformed input
        │   │       └── training/                   # Flat records and existing SFT training sets:
        │   │           ├── records_2023-24.jsonl   # 34,217 flat cutoff records for 2023-24 (25.1 MB)
        │   │           ├── records_2024-25.jsonl   # Flat cutoff records for 2024-25 (28.2 MB)
        │   │           ├── records_2025-26.jsonl   # Flat cutoff records for 2025-26 (33.8 MB)
        │   │           ├── all_records.csv         # Reconciled CSV of all cutoff rows across years (49.2 MB)
        │   │           └── sft_grounded_qa.jsonl   # 20,001 chat-format Q&A examples for behavioural SFT (24.2 MB)
        │   │
        │   ├── phase3_final_staging/               # Canonical, validated multi-year hierarchical cutoffs
        │   │   ├── 2020-21/                        # Canonical <institute_code>.json files
        │   │   ├── 2021-22/                        # Canonical <institute_code>.json files
        │   │   ├── 2022-23/                        # Canonical <institute_code>.json files
        │   │   ├── 2023-24/                        # 332 canonical <institute_code>.json files
        │   │   ├── 2024-25/                        # Canonical <institute_code>.json files
        │   │   └── 2025-26/                        # Canonical <institute_code>.json files
        │   │
        │   └── college_ai_consultant_sparse_enriched_v4_no_cutoffs/ # 1,041 verified sparse college JSONs
        │       ├── dataset_manifest.json           # Manifest with verification hashes & schema
        │       ├── college_dataset_index.csv       # Master CSV index mapping MHHEI IDs to names & codes
        │       └── MHHEI_00001.json ... MHHEI_01041.json # Individual college qualitative profiles
        │
        ├── scripts/                                # Processing scripts, adapters, and engines
        │   ├── college_adapter.py                  # Normalizes MHHEI JSON structures for indexing
        │   ├── validate_dataset.py                 # Validates the 1,041 college dataset against schemas
        │   ├── validate_cutoffs.py                 # Semantic and schema validation for cutoff JSONs
        │   ├── adapt_cutoff_data.py                # Adapts raw extracted cutoffs to canonical hierarchy
        │   ├── extract_historical_cutoffs.py       # Ingests legacy 2020-2023 cutoff PDFs
        │   ├── reconcile_staging.py                # Merges multi-year adapted cutoffs & audits conflicts
        │   ├── convert_to_training_data.py         # Converts hierarchical cutoffs & info into SFT chat JSONL
        │   ├── build_vector_index.py               # Indexes college info into ChromaDB vector database
        │   ├── rag_pipeline.py                     # High-level entry point wiring agents, RAG, and LLM
        │   ├── ollama_client.py                    # Offline client for local Ollama daemon (Qwen2.5)
        │   ├── admission_rules.py                  # Deterministic CAP quota & eligibility rules engine
        │   ├── cutoff_analyzer.py                  # Multi-year cutoff trend & round shift analysis engine
        │   ├── recommendation_engine.py            # Transparent candidate option classification (Attainable/Reach)
        │   ├── option_planner.py                   # Generates balanced CAP option form preference strategies
        │   │
        │   └── agents/                             # Modular agent layer
        │       ├── college_resolver.py             # Resolves colloquial college names & ambiguous inputs
        │       ├── college_info_agent.py           # Semantic retrieval agent over Chroma vector DB
        │       ├── cutoff_agent.py                 # Deterministic structured cutoff lookup agent
        │       └── orchestrator.py                 # Master intent classifier and agent router
        │
        ├── reports/                                # Validation and extraction audit reports
        │   └── validation_report.json              # Audit report for college sparse dataset
        │
        └── tests/                                  # 100% offline regression & unit test suite
            ├── test_college_adapter.py             # Unit tests for college data adapter
            ├── test_college_resolver.py            # Unit tests for name/code resolution & ambiguity detection
            ├── test_validation.py                  # Unit tests for college schema validation
            ├── test_chroma_indexing.py             # Integration tests for vector database index
            ├── test_phase1a_college_info.py        # Regression tests for baseline Phase 1A
            ├── test_phase2_llm_rag.py              # Unit tests for local LLM + RAG + Ollama integration
            ├── test_orchestrator_pipeline.py       # Unit tests for orchestrator routing logic
            └── test_phase3_admission_intelligence.py # Tests for rules, analyzer, planner, & recommender
```

---

## 2. Cutoff Data Pipeline: Source Formats & Representations

Understanding the data representations across the pipeline is essential for converting cutoffs into training data:

### Level 1: Raw CET Cell Cutoff PDF Formats
Maharashtra State CET Cell publishes two distinct PDF formats:
* **Format B ("state_level" / "maharashtra_minority")**:
  - Contains sections: *State Level*, *Home University Seats Allotted to Home University Candidates*, *Other Than Home University Seats...*
  - Tables organize columns by seat category (e.g. `GOPENS`, `GSCS`, `TFWS`, `EWS`, `LOBCH`).
  - Rows represent Stages (e.g., `Stage-I`, `Stage-II`) containing pairs of **Closing Merit Rank** and `(Closing Percentile)`.
* **Format A ("all_india")**:
  - A flat table for All India seats allotted through JEE (Main) or MHT-CET merit.
  - Columns: `Sr. No`, `Merit No (Percentile)`, `Choice Code`, `Institute Name`, `Course Name`, `Exam`, `Seat Type`.

### Level 2: Raw Extracted JSON (`cutoffs/raw_extracted/V4_daataa/<year>/<slug>.json`)
Produced by `extract_data_v4.py`. Groups all branches for an institution into a single JSON per year:
```json
{
  "academic_year": "2023-24",
  "institute_code": "1002",
  "institute_name": "Government College of Engineering, Amravati",
  "status": "Government Autonomous",
  "branches": [
    {
      "course_code": "100219110",
      "branch": "Civil Engineering",
      "branch_family": "civil",
      "categories": [
        {
          "category": "DEFOPENS",
          "category_meaning": "Defense quota, Open, State Level",
          "cutoffs": [
            {
              "round": 1,
              "stage": 1,
              "level_key": "state_level",
              "list_type": "maharashtra_minority",
              "closing_rank": 114710,
              "closing_percentile": 36.1619626,
              "evidence_id": "2023-24:1002:100219110:state_level:DEFOPENS:R1:S1",
              "source_file": "2023ENGG_CAP1_CutOff.pdf",
              "page": 1
            }
          ]
        }
      ]
    }
  ]
}
```

### Level 3: Canonical Hierarchical Staging (`cutoffs/phase3_final_staging/<year>/<institute_code>.json`)
Produced by `adapt_cutoff_data.py` and `reconcile_staging.py`.
* Canonicalizes 4-digit college codes to standard 5-digit strings (e.g. `"1002"` -> `"01002"`).
* Standardizes list types to `"CAP"` or `"All India"`.
* Cross-referenced and verified against `college_dataset_index.csv`.

### Level 4: Flat Tabular Records (`cutoffs/raw_extracted/V4_daataa/training/records_<year>.jsonl` & `all_records.csv`)
Each row represents a single category cutoff observation:
```json
{
  "academic_year": "2023-24",
  "cap_round": 1,
  "stage": 1,
  "list_type": "all_india",
  "institute_code": "6006",
  "institute_name": "COEP Technological University",
  "course_code": "600624510",
  "course_name": "Computer Engineering",
  "seat_type": "AI",
  "closing_rank": 98,
  "closing_percentile": 99.7006242,
  "exam": "JEE(Main)",
  "evidence_id": "2023-24:6006:600624510:all_india:AI:R1:S1",
  "branch_family": "computing"
}
```

---

## 3. Methods to Convert Cutoff Data for Model Training

We have two distinct modeling paradigms, each requiring a specific dataset structure:

```
                          Cutoff Folder Data Sources
           (cutoffs/phase3_final_staging/ & raw_extracted/V4_daataa/)
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
        [Task A: Generative LLM]              [Task B: Tabular ML Predictor]
        Behavioural SFT Chat JSONL             Multi-Year Feature Table CSV
        - Citation of [evidence_id]           - Features: College, Branch, Quota,
        - Grounded Q&A Format                   Round, Historical Rank shifts
        - Abstention on missing facts         - Target: Expected Closing Rank &
        - Conflict surfacing                    Closing Percentile intervals
```

### 3.1. Format A: Conversational SFT JSONL (For LLM Behaviour Fine-Tuning)
The conversational format is fully compatible with OpenAI, Unsloth, Hugging Face TRL (`SFTTrainer`), and Axolotl.

Each line is a single JSON object containing a `messages` array:
```json
{
  "messages": [
    {"role": "system", "content": "<SYSTEM_PROMPT>"},
    {"role": "user", "content": "EVIDENCE:\n<RETRIEVED_EVIDENCE_LINES>\n\nQUESTION: <STUDENT_QUESTION>"},
    {"role": "assistant", "content": "<GROUNDED_ANSWER_WITH_CITATIONS_AND_DISCLAIMER>"}
  ],
  "type": "grounded"
}
```

#### The Three Core Behavioural Templates

#### 1. Grounded Cutoff Observation Template (`type: "grounded"`)
* **System Prompt:**
  ```text
  You are an admission decision-support assistant for Maharashtra engineering colleges. Use only the supplied evidence. Cite evidence IDs in [brackets]. Never promise admission. A historical cutoff describes a past round's outcome, not a guarantee for any future round or year. If evidence is missing, respond with status=insufficient_evidence and say exactly what is missing.
  ```
* **User Input:**
  ```text
  EVIDENCE:
  [2024-25:01002:0100219110:state_level:GOPENS:R1:S1] 2024-25 CAP round 1 stage 1 | State Level | GOPENS: closing rank 42150, percentile 82.1402911
  [2024-25:01002:0100219110:state_level:GOPENS:R2:S1] 2024-25 CAP round 2 stage 1 | State Level | GOPENS: closing rank 48920, percentile 79.5412003

  QUESTION: What were the GOPENS closing cutoffs for Civil Engineering at Government College of Engineering, Amravati in 2024-25?
  ```
* **Assistant Output:**
  ```text
  Historical observation from the supplied records:
  - Round 1, stage 1: rank 42150, percentile 82.1402911 [2024-25:01002:0100219110:state_level:GOPENS:R1:S1]
  - Round 2, stage 1: rank 48920, percentile 79.5412003 [2024-25:01002:0100219110:state_level:GOPENS:R2:S1]

  This describes 2024-25 only - not a prediction or guarantee for any other year. Confirm against the official CET Cell notice before relying on it.
  ```

#### 2. Abstention Template (`type: "abstention"`)
When a student asks for a category/round not present in the evidence, the model must **refuse** rather than invent cutoffs:
* **User Input:**
  ```text
  EVIDENCE:
  [2024-25:01002:0100219110:state_level:GOPENS:R1:S1] 2024-25 CAP round 1 stage 1 | State Level | GOPENS: closing rank 42150

  QUESTION: What was the GSTS closing cutoff for Civil Engineering at Government College of Engineering, Amravati in 2024-25?
  ```
* **Assistant Output (JSON structured refusal):**
  ```json
  {
    "status": "insufficient_evidence",
    "missing_information": ["GSTS record for Civil Engineering at Government College of Engineering, Amravati, 2024-25"],
    "next_action": "Check the official CET Cell cutoff list for this seat type, or confirm this category was offered at this college this year."
  }
  ```

#### 3. Qualitative College Information & Conflict Surfacing (`type: "college_info"`)
When secondary sources disagree (e.g. established year reported as 2008 vs 1983):
* **Assistant Output:**
  ```text
  The sources I have disagree on this, so I will show the conflict rather than pick one:
  - established_year: CONFLICTING SOURCES - 1983 per official_master; 2008 per secondary_portal

  Verify directly with the institute or an official source before relying on any single figure here.
  ```

---

### 3.2. Data Conversion Implementation Details

#### Method 1: Using the Existing Script (`convert_to_training_data.py`)
This script processes canonical year folders and sparse college info into SFT chat format:

```powershell
python scripts/convert_to_training_data.py `
  --cutoffs cutoffs/phase3_final_staging `
  --college-info cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs `
  --out cutoffs/training/sft_combined_dataset.jsonl `
  --max-cutoff-examples 10000 `
  --abstention-examples 1000 `
  --seed 42
```

#### Method 2: Custom Multi-Year Comprehensive Builder
To generate a comprehensive dataset merging historical trends, round progressions, and abstentions, create a dedicated converter script:

```python
# Save as: scripts/generate_complete_sft_dataset.py
import json
import random
from pathlib import Path

def generate_multiyear_sft(staging_dir, out_file, sample_size=15000):
    staging_path = Path(staging_dir)
    records = []
    
    # 1. Iterate over all years in staging
    for year_dir in sorted(staging_path.iterdir()):
        if not year_dir.is_dir():
            continue
        year = year_dir.name
        
        for college_file in year_dir.glob("*.json"):
            try:
                data = json.loads(college_file.read_text(encoding="utf-8"))
            except Exception:
                continue
                
            inst_name = data.get("institute_name")
            inst_code = data.get("institute_code")
            
            for branch in data.get("branches", []):
                branch_name = branch.get("branch")
                for cat in branch.get("categories", []):
                    cat_name = cat.get("category")
                    cutoffs = [c for c in cat.get("cutoffs", []) if c.get("closing_rank") is not None]
                    if not cutoffs:
                        continue
                        
                    # Format evidence lines
                    ev_lines = []
                    answer_lines = []
                    for c in cutoffs:
                        ev_id = c.get("evidence_id")
                        r = c.get("round")
                        s = c.get("stage")
                        rank = c.get("closing_rank")
                        pct = c.get("closing_percentile")
                        
                        ev_lines.append(f"[{ev_id}] {year} CAP round {r} stage {s} | {cat_name}: closing rank {rank}, percentile {pct}")
                        answer_lines.append(f"- Round {r}, stage {s}: rank {rank}, percentile {pct} [{ev_id}]")
                        
                    q = f"What were the {cat_name} cutoffs for {branch_name} at {inst_name} ({inst_code}) in {year}?"
                    a = (
                        "Historical observation from the supplied records:\n" +
                        "\n".join(answer_lines) +
                        f"\nThis describes {year} only. It is not a prediction or guarantee for future rounds. "
                        "Confirm against official CET Cell notifications."
                    )
                    
                    records.append({
                        "messages": [
                            {"role": "system", "content": "You are an admission decision-support assistant. Use only supplied evidence. Cite evidence IDs in [brackets]."},
                            {"role": "user", "content": f"EVIDENCE:\n" + "\n".join(ev_lines) + f"\n\nQUESTION: {q}"},
                            {"role": "assistant", "content": a}
                        ],
                        "type": "grounded"
                    })
                    
    random.seed(42)
    random.shuffle(records)
    selected = records[:sample_size]
    
    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in selected:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            
    print(f"Generated {len(selected)} SFT examples saved to {out_file}")

if __name__ == "__main__":
    generate_multiyear_sft(
        staging_dir="cutoffs/phase3_final_staging",
        out_file="cutoffs/training/sft_multiyear_training.jsonl",
        sample_size=15000
    )
```

---

## 4. End-to-End Steps & Commands for Training the Model

Below is the complete step-by-step procedure with PowerShell commands and Python scripts. **No commands have been run; this is your complete operational playbook.**

---

### Step 1: Python Environment Setup (Windows PowerShell)

Ensure Python 3.10, 3.11, or 3.12 (64-bit) with CUDA 12.1+ support is installed.

```powershell
# 1. Navigate to the core workspace directory
Set-Location -Path "c:\Users\om70c\Downloads\AI-cons\AI-cons\model_rag_agent_plan"

# 2. Create and activate a clean virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Upgrade build tools
python -m pip install --upgrade pip setuptools wheel

# 4. Install PyTorch with CUDA support (for NVIDIA RTX 4060 / Ampere / Ada)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 5. Install RAG, Vector Search, and Extraction dependencies
pip install -r requirements.txt

# 6. Install Fine-Tuning & Quantization toolkits
pip install unsloth trl peft bitsandbytes datasets accelerate transformers
```

---

### Step 2: Validate & Prepare the Datasets

Before converting to training format, execute deterministic dataset audits:

```powershell
# 1. Run full unit and integration regression test suite (9 test suites)
python -m unittest discover tests -v

# 2. Validate the 1,041-college verified sparse dataset
python scripts/validate_dataset.py

# 3. Validate historical cutoff JSONs across all staged academic cycles
python scripts/validate_cutoffs.py --dir cutoffs/phase3_final_staging

# 4. Build the master vector index for RAG retrieval
python scripts/build_vector_index.py `
  --college-info cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs `
  --out ./vector_index `
  --rebuild
```

---

### Step 3: Convert Cutoff Staging Data into SFT Chat JSONL

Generate the fine-tuning dataset with grounded citations, abstentions, and college info:

```powershell
# 1. Convert phase3 canonical staging to SFT format
python scripts/convert_to_training_data.py `
  --cutoffs cutoffs/phase3_final_staging `
  --college-info cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs `
  --out cutoffs/training/sft_training_final.jsonl `
  --max-cutoff-examples 12000 `
  --abstention-examples 1500 `
  --seed 42

# 2. Split dataset into train (90%) and validation (10%) splits
python -c @"
import json, random
from pathlib import Path
lines = [line for line in Path('cutoffs/training/sft_training_final.jsonl').read_text(encoding='utf-8').strip().split('\n') if line]
random.seed(42)
random.shuffle(lines)
split = int(len(lines) * 0.9)
Path('cutoffs/training/train.jsonl').write_text('\n'.join(lines[:split]), encoding='utf-8')
Path('cutoffs/training/val.jsonl').write_text('\n'.join(lines[split:]), encoding='utf-8')
print(f'Train samples: {split}, Validation samples: {len(lines) - split}')
"@
```

---

### Step 4: QLoRA Fine-Tuning Script (`train_qwen_qlora.py`)

Create the fine-tuning script. This script applies QLoRA (4-bit quantization, rank 16) to `Qwen2.5-7B-Instruct` (or `Qwen2.5-3B-Instruct` for 8GB VRAM limits):

```python
# Save as: scripts/train_qwen_qlora.py
"""
QLoRA Behaviour Fine-Tuning for AI-con
Trains Qwen2.5 on evidence citation, abstention, and structured anti-hallucination outputs.
"""
import os
import torch
from datasets import load_dataset
from transformers import TrainingArguments
from trl import SFTTrainer
from unsloth import FastLanguageModel

# Hyperparameters
MAX_SEQ_LENGTH = 2048
MODEL_NAME = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"  # Alternatively: unsloth/Qwen2.5-3B-Instruct-bnb-4bit
OUTPUT_DIR = "./lora_qwen_aicon_checkpoints"

def main():
    print(f"Loading 4-bit base model: {MODEL_NAME}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        dtype=None,  # Auto-detected (Float16 or Bfloat16)
    )

    # Configure PEFT / LoRA adapter
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing=True,
        random_state=42,
    )

    # Load preprocessed datasets
    dataset = load_dataset(
        "json",
        data_files={
            "train": "cutoffs/training/train.jsonl",
            "validation": "cutoffs/training/val.jsonl",
        }
    )

    # Formatting function for chat messages
    def format_chat_template(batch):
        texts = []
        for conversation in batch["messages"]:
            text = tokenizer.apply_chat_template(
                conversation,
                tokenize=False,
                add_generation_prompt=False
            )
            texts.append(text)
        return {"text": texts}

    dataset = dataset.map(format_chat_template, batched=True)

    # Training configuration
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_ratio=0.05,
        num_train_epochs=2,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=20,
        evaluation_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=2,
        optim="adamw_8bit",
        seed=42,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        args=training_args,
    )

    print("Starting QLoRA fine-tuning...")
    trainer.train()

    # Save fine-tuned LoRA adapters
    final_adapter_dir = "./lora_aicon_final"
    model.save_pretrained(final_adapter_dir)
    tokenizer.save_pretrained(final_adapter_dir)
    print(f"LoRA adapters successfully saved to: {final_adapter_dir}")

    # Export merged 16-bit model for inference / quantization
    merged_model_dir = "./qwen_aicon_merged_16bit"
    print(f"Saving merged full-precision model to: {merged_model_dir}")
    model.save_pretrained_merged(merged_model_dir, tokenizer, save_method="merged_16bit")

if __name__ == "__main__":
    main()
```

#### Execute Training Command:
```powershell
python scripts/train_qwen_qlora.py
```

---

### Step 5: Convert & Quantize to GGUF for Local Inference

To deploy the fine-tuned model offline in Ollama or llama.cpp:

```powershell
# 1. Clone llama.cpp repository
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp

# 2. Install llama.cpp conversion dependencies
pip install -r requirements.txt

# 3. Convert merged model to GGUF (FP16)
python convert_hf_to_gguf.py ../qwen_aicon_merged_16bit --outfile ../qwen2.5-aicon-f16.gguf

# 4. Quantize to Q5_K_M (matching the repo's qwen2.5-coder-3b GGUF)
.\llama-quantize ../qwen2.5-aicon-f16.gguf ../qwen2.5-aicon-q5_k_m.gguf Q5_K_M

cd ..
```

---

### Step 6: Serve Locally via Ollama

Register the quantized model with Ollama:

1. Create a `Modelfile`:
```dockerfile
# Save as: Modelfile
FROM ./qwen2.5-aicon-q5_k_m.gguf

PARAMETER temperature 0.0
PARAMETER top_p 0.95
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|>"

SYSTEM """You are an admission decision-support assistant for Maharashtra engineering colleges. Use only the supplied evidence. Cite evidence IDs in [brackets]. Never promise admission. If evidence is missing, answer with status=insufficient_evidence."""
```

2. Register and start model in Ollama:
```powershell
# Create model in Ollama library
ollama create qwen2.5-aicon:latest -f Modelfile

# Test model via Ollama CLI
ollama run qwen2.5-aicon:latest "Tell me about Government College of Engineering, Amravati"
```

---

### Step 7: Wire Fine-Tuned Model into the RAG Pipeline

Run end-to-end questions through the full pipeline (`rag_pipeline.py`):

```powershell
# 1. College Information Query (Vector RAG)
python scripts/rag_pipeline.py `
  --vector-index ./vector_index `
  --model "qwen2.5-aicon:latest" `
  --question "What is the affiliation and autonomy status of Government College of Engineering, Amravati?"

# 2. Historical Cutoff Query (Exact Structured Lookup)
python scripts/rag_pipeline.py `
  --cutoffs cutoffs/phase3_final_staging `
  --vector-index ./vector_index `
  --model "qwen2.5-aicon:latest" `
  --question "What was the GOPENS cutoff for Computer Engineering at COEP in 2024-25?"

# 3. Missing Evidence Query (Testing Abstention)
python scripts/rag_pipeline.py `
  --cutoffs cutoffs/phase3_final_staging `
  --vector-index ./vector_index `
  --model "qwen2.5-aicon:latest" `
  --question "What was the GSTS cutoff for Aeronautics Engineering at Indala College in 2024-25?"
```

---

## 5. Summary Quality & Validation Checklist

Before releasing or deploying any newly fine-tuned model checkpoint, verify the following gates:

| Gate | Requirement | Pass Criteria |
|---|---|---|
| **1. Citation Precision** | Every factual statement cites an `[evidence_id]` | 100% of generated numbers accompanied by bracketed ID |
| **2. Abstention Accuracy** | When requested category/seat type is not in evidence | Returns `status=insufficient_evidence` without guessing |
| **3. Zero Number Invention** | No hallucinated ranks or percentiles | Output numbers must strictly match retrieved JSON facts |
| **4. Metric Independence** | Rank and Percentile are never mathematically conflated | Integers for ranks, floats with decimal precision for percentiles |
| **5. Disclaimer Compliance** | Clear advisory notice attached to every cutoff output | Flags that cutoffs describe past years, not admission guarantees |
| **6. Unit Regression** | All Phase 1, Phase 2, and Phase 3 tests pass | `python -m unittest discover tests -v` exits with code 0 |

---
*Created for the AI-con Maharashtra Engineering Admissions Counselling Project.*
