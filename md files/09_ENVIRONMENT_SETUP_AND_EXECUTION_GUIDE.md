# AI-CON: Environment Setup & Execution Guide

**Document ID:** AI-CON-ENV-09  
**Target Operating Systems:** Windows 10/11 (PowerShell) / Linux (Bash)  
**Target Python Version:** Python 3.10.x (Recommended: 3.10.11)  

---

## 1. System Prerequisites

Before starting, ensure your host machine meets the following minimum requirements:

| Component | Minimum Specification | Recommended Specification |
|:---|:---|:---|
| **Operating System** | Windows 10/11 64-bit or Ubuntu 22.04 LTS | Windows 11 64-bit or Ubuntu 22.04 |
| **CPU** | Quad-core Intel Core i5 / AMD Ryzen 5 | 8-core Intel Core i7 / AMD Ryzen 7 |
| **System RAM** | 16 GB DDR4 | 32 GB DDR5 |
| **Storage** | 20 GB free SSD space | 50 GB free NVMe SSD |
| **Dedicated GPU** | None (CPU inference supported) | NVIDIA GeForce RTX 3060 / 4060 (8GB+ VRAM) |
| **Python** | Python 3.10.8 to 3.10.12 | Python 3.10.11 |
| **LLM Server** | Ollama v0.1.30+ | Ollama v0.3.0+ |

---

## 2. Step-by-Step Installation from Scratch

### Step 1: Open Terminal & Navigate to Project Workspace
```powershell
Set-Location "C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons\AI-cons\AI-cons\model_rag_agent_plan"
```

### Step 2: Initialize Clean Python Virtual Environment
```powershell
# Create isolated Python 3.10 virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

### Step 3: Upgrade Pip & Install Base Requirements
```powershell
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### Step 4: Install ReportLab & Evaluation Dependencies
```powershell
pip install reportlab pdfplumber
```

### Step 5: (Optional for GPU Fine-Tuning) Install CUDA-Enabled PyTorch
If you intend to run QLoRA 4-bit fine-tuning with `scripts/train_qwen_lora.py` on your NVIDIA GPU:

```powershell
# Install PyTorch with CUDA 12.1 runtime
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 --upgrade

# Install bitsandbytes
pip install bitsandbytes>=0.43.0

# Verify CUDA availability
python -c "import torch; print('CUDA Available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

---

## 3. Ollama Serving Engine Setup

Local conversational inference requires Ollama running locally.

### Step 1: Download & Install Ollama
Download and run the Windows installer from [https://ollama.com/download](https://ollama.com/download).

### Step 2: Verify Ollama Service
Open a separate PowerShell window and verify the daemon is active:
```powershell
ollama --version
curl http://localhost:11434/api/tags
```

### Step 3: Pull Foundation Models
```powershell
# 1. Pull Qwen 2.5 7B Reference Model (4.7 GB)
ollama pull qwen2.5:7b

# 2. Pull TinyLlama Base Model (637 MB)
ollama pull tinyllama

# 3. Pull / Configure AI-CON Model (2.4 GB)
ollama pull qwen2.5-coder:3b
```

### Step 4: Create `qwen2.5-aicon` Custom Model
In the project directory, register the tailored AI-CON Modelfile:
```powershell
@'
FROM qwen2.5-coder:3b
SYSTEM "You are an admission decision-support assistant for Maharashtra engineering colleges. Use only the supplied evidence. Cite evidence IDs in [brackets]. Never promise admission. If evidence is missing, answer with status=insufficient_evidence."
PARAMETER temperature 0
PARAMETER top_p 0.95
'@ | Set-Content Modelfile

ollama create qwen2.5-aicon:latest -f Modelfile
```

---

## 4. Reproducing the Complete Pipeline

Execute the following commands sequentially to regenerate all data, indices, models, and evaluation reports:

### 1. Build ChromaDB Vector Index (1,041 College Profiles)
```powershell
python scripts/build_vector_index.py
# Output: Indexed 1,041 chunks into vector_index/chroma.sqlite3
```

### 2. Generate Training Datasets (CSV & SFT JSONL)
```powershell
python scripts/convert_to_training_data.py
# Output: Generated cutoff_tabular_features.csv (116,744 rows) & sft_training_final.jsonl (12,041 pairs)
```

### 3. Train Tabular Regressors (Closing Rank & Percentile)
```powershell
python scripts/train_model.py
# Output: Saved cutoff_regressor_rank.joblib & cutoff_regressor_percentile.joblib (Duration: ~2.7s)
```

### 4. Run Full Unit Test Regression Suite
```powershell
python -m unittest discover tests
# Output: Ran 111 tests in 0.48s -> OK (skipped=2)
```

### 5. Run 5-Level Progressive Benchmark Test
```powershell
python scripts/run_5_level_test.py
# Output: Saved model_artifacts/five_level_test_results.json
```

### 6. Compile 22-Page Publication PDF Report
```powershell
python AI_CON_Evaluation_Report/generate_report.py
# Output: Saved AI_CON_Model_Evaluation_Report.pdf (22 pages) & AI_CON_Evaluation_Report.zip
```
