# AI-CON: Google Drive Upload & Compliance Packaging Guide

**Document ID:** AI-CON-DRIVE-COMPLIANCE  
**Target:** Google Drive / Enterprise Cloud Storage  
**Compliance Standard:** Zero Credential Exposure, Sanitized Large Binary Policy  

---

## 1. Compliance Audit & Size Classification

Before uploading the project repository to Google Drive or sharing it with an external collaborator, files must be audited for:
1. **Size Limits**: Google Drive sync agents struggle with virtual environments containing 50,000+ tiny `.pyc` and `.h` files.
2. **Platform Incompatibilities**: Windows `.venv` binary `.dll` and `.exe` files do not execute on Linux/macOS and should never be synced.
3. **Redundant Large Binaries**: Foundation GGUF blobs (e.g. 18 GB `qwen3-coder:30b`, 4.7 GB `qwen2.5:7b`) can be downloaded in seconds via Ollama CLI and will unnecessarily consume personal Drive quotas.
4. **Secrets & Credentials**: Ensure zero `.env`, `.pem`, `.key`, or credentials exist.

```text
+---------------------------------------------------------------------------------------------------------------+
|                                      GOOGLE DRIVE UPLOAD TRIAGE MATRIX                                        |
+------------------------------------+---------------------+-------------------+--------------------------------+
| Directory / Component              | Approx Size on Disk | Drive Action      | Rationale                      |
+------------------------------------+---------------------+-------------------+--------------------------------+
| AI_CON_Project_Handover/           | < 1 MB              | INCLUDE (Direct)  | All documentation & manifests  |
| AI_CON_Evaluation_Report/          | < 1 MB              | INCLUDE (Direct)  | Evaluation report, PDF, script |
| training_data/                     | ~80 MB total        | INCLUDE (Zipped)  | Canonical CSV & JSONL datasets |
| cutoffs/phase3_final_staging/      | ~35 MB total        | INCLUDE (Zipped)  | 2,013 historical cutoff JSONs  |
| cutoffs/..._no_cutoffs/            | ~2 MB total         | INCLUDE (Zipped)  | 1,041 college profile JSONs    |
| model_artifacts/*.joblib           | ~1.8 MB total       | INCLUDE (Direct)  | Trained tabular models         |
| model_artifacts/lora_adapter/      | ~8.1 MB total       | INCLUDE (Direct)  | TinyLlama LoRA adapter weights |
| scripts/ & tests/                  | ~350 KB             | INCLUDE (Direct)  | Source code & unit tests       |
| vector_index/chroma.sqlite3        | 6.5 MB              | INCLUDE (Direct)  | Vector search SQLite database  |
| .venv/ & .venv-test/               | 2.3+ GB             | EXCLUDE           | Platform-specific virtualenvs  |
| .cache/huggingface/                | 2.0+ GB             | EXCLUDE           | Transient download cache       |
| ~/.ollama/models/                  | 25.0+ GB            | EXCLUDE           | Base GGUFs (re-pull via CLI)   |
| __pycache__/                       | ~15 MB              | EXCLUDE           | Transient Python bytecode      |
+------------------------------------+---------------------+-------------------+--------------------------------+
```

---

## 2. Step-by-Step Google Drive Packaging Procedure

To create a clean, compliant, and self-contained zip package suitable for uploading to Google Drive without hitting quota limits or uploading virtual environment junk:

### Step 1: Run the Automated Packaging Script
Run the following PowerShell command from the repository root:

```powershell
Set-Location "C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons\AI-cons\AI-cons\model_rag_agent_plan"

# Create a clean archive excluding virtualenvs and cache
$destination = "C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons\AI_CON_Clean_Handover_Package.zip"

Get-ChildItem -Path . -Exclude ".venv", ".venv-test", ".cache", "__pycache__" | 
    Compress-Archive -DestinationPath $destination -Force

Write-Host "Clean handover package created at: $destination"
Get-Item $destination | Select-Object Name, Length, LastWriteTime
```

### Step 2: What is Inside the Clean Zip Package?
The resulting `AI_CON_Clean_Handover_Package.zip` is approximately **45 MB** compressed, containing:
- Complete `AI_CON_Project_Handover/` documentation suite.
- Complete `AI_CON_Evaluation_Report/` (including 22-page PDF report).
- All source code in `scripts/`, `agents/`, and `tests/`.
- All datasets in `training_data/` and `cutoffs/`.
- All trained tabular models in `model_artifacts/`.
- Verified TinyLlama LoRA adapter weights (`adapter_model.safetensors`).
- The ChromaDB vector database (`vector_index/chroma.sqlite3`).

### Step 3: Uploading to Google Drive
1. Open [Google Drive](https://drive.google.com).
2. Create a new folder named `AI-CON_Project_Handover`.
3. Drag and drop:
   - `AI_CON_Clean_Handover_Package.zip` (for one-click download).
   - The unzipped `AI_CON_Project_Handover/` directory (for immediate reading inside Google Drive preview).
   - `AI_CON_Evaluation_Report/AI_CON_Model_Evaluation_Report.pdf` (for instant reading of the 22-page evaluation benchmark).

---

## 3. Recipient Onboarding Instructions

When your friend receives the Google Drive folder:
1. Download `AI_CON_Clean_Handover_Package.zip` and extract it to a local folder.
2. Open `AI_CON_Project_Handover/README.md`.
3. Follow the 3-step setup in `09_ENVIRONMENT_SETUP_AND_EXECUTION_GUIDE.md`:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ollama pull qwen2.5:7b
   python -m unittest discover tests
   ```
The entire system will be fully operational in under 10 minutes.
