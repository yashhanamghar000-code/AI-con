# AI-CON Handover File Manifest & Asset Inventory

**Manifest Version:** 1.0.0  
**Generated Date:** October 2026  
**Project Workspace:** `C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons\AI-cons\AI-cons\model_rag_agent_plan`  
**Handover Folder:** `C:\Users\Yash Hanamghar.Nyai\Downloads\AI-cons\AI_CON_Project_Handover`  

---

## 1. Handover Documentation Package Manifest

These documents constitute the complete handover documentation package located in `AI_CON_Project_Handover/`:

| File Name | File Size | Primary Purpose & Contents |
|:---|:---:|:---|
| [`README.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/README.md) | ~5.2 KB | Collaborator onboarding, executive summary, 5-minute smoke test, and navigation index. |
| [`HANDOVER_MANIFEST.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/HANDOVER_MANIFEST.md) | ~12.5 KB | This master file manifest, file paths, verified sizes, and Google Drive classifications. |
| [`01_PROJECT_OVERVIEW_AND_ARCHITECTURE.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/01_PROJECT_OVERVIEW_AND_ARCHITECTURE.md) | ~14.0 KB | CAP admissions problem domain, 4-tier hybrid pipeline architecture, flowcharts, and component roles. |
| [`02_SOURCE_CODE_AND_MODULE_EXPLANATIONS.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/02_SOURCE_CODE_AND_MODULE_EXPLANATIONS.md) | ~22.0 KB | Detailed technical audit of all 21 scripts across `scripts/`, `agents/`, and `tests/`. |
| [`03_DATASET_INVENTORY_AND_RECORD_COUNTS.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/03_DATASET_INVENTORY_AND_RECORD_COUNTS.md) | ~15.0 KB | Verified row counts, file sizes, data lineage (CET PDF -> Staging -> SFT/Tabular), and split ratios. |
| [`04_DATA_MODELS_SCHEMAS_AND_RELATIONSHIPS.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/04_DATA_MODELS_SCHEMAS_AND_RELATIONSHIPS.md) | ~18.0 KB | Entity-Relationship diagrams, JSON schemas, CSV headers, data types, and primary key relationships. |
| [`05_MODEL_INVENTORY_AND_CONFIGURATIONS.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/05_MODEL_INVENTORY_AND_CONFIGURATIONS.md) | ~16.0 KB | Tabular HistGradientBoosting models, Ollama GGUFs, TinyLlama LoRA adapter, and Qwen 3B specs. |
| [`06_TRAINING_PIPELINE_AND_LOGS.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/06_TRAINING_PIPELINE_AND_LOGS.md) | ~17.0 KB | Step-by-step training pipeline, tabular execution, TinyLlama LoRA logs, and QLoRA GPU prerequisites. |
| [`07_INFERENCE_AND_API_INTEGRATION.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/07_INFERENCE_AND_API_INTEGRATION.md) | ~15.0 KB | Production inference API, Orchestrator usage, Ollama HTTP REST interface, and Python examples. |
| [`08_BENCHMARK_EVALUATION_AND_ANALYSIS.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/08_BENCHMARK_EVALUATION_AND_ANALYSIS.md) | ~20.0 KB | 5-Level benchmark evaluation results, verbatim answers, `92.40 < 95.00` failure analysis, and scorecard. |
| [`09_ENVIRONMENT_SETUP_AND_EXECUTION_GUIDE.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/09_ENVIRONMENT_SETUP_AND_EXECUTION_GUIDE.md) | ~16.0 KB | Clean setup from scratch: Python 3.10 virtualenv, Ollama pull, CUDA PyTorch upgrade, unit test verification. |
| [`10_KNOWN_ISSUES_AND_FUTURE_ROADMAP.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/10_KNOWN_ISSUES_AND_FUTURE_ROADMAP.md) | ~14.0 KB | Current technical blockers (CPU PyTorch, bitsandbytes), mitigations, and phased engineering roadmap. |
| [`GOOGLE_DRIVE_UPLOAD_AND_COMPLIANCE_GUIDE.md`](file:///C:/Users/Yash%20Hanamghar.Nyai/Downloads/AI-cons/AI_CON_Project_Handover/GOOGLE_DRIVE_UPLOAD_AND_COMPLIANCE_GUIDE.md) | ~10.0 KB | File size auditing, Google Drive upload recommendations, exclusion lists, and zip packaging manifest. |

---

## 2. Core Repository Artifacts & Verification Table

### 2.1 Tabular & Supervised Datasets (`training_data/`)
| File Relative Path | Exact File Size | Record / Row Count | Format | Google Drive Suitability |
|:---|:---:|:---:|:---:|:---|
| `training_data/cutoff_tabular_features.csv` | 49,137,158 bytes (46.86 MB) | 116,744 rows | CSV (24 cols) | Safe for Drive (< 100 MB). |
| `training_data/sft_training_final.jsonl` | 15,112,239 bytes (14.41 MB) | 12,041 pairs | JSONL (ChatML) | Safe for Drive. |
| `training_data/train.jsonl` | 13,597,795 bytes (12.97 MB) | 10,836 pairs | JSONL (90% train) | Safe for Drive. |
| `training_data/val.jsonl` | 1,514,444 bytes (1.44 MB) | 1,205 pairs | JSONL (10% val) | Safe for Drive. |
| `training_data/sample_sft.jsonl` | 1,758,364 bytes (1.68 MB) | 1,161 pairs | JSONL (Smoke test) | Safe for Drive. |

### 2.2 Historical Cutoffs & College Profiles (`cutoffs/`)
| Directory / File Path | Item Count / Size | Primary Entity | Format | Google Drive Suitability |
|:---|:---:|:---:|:---:|:---|
| `cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs/` | 1,041 JSON files + index (1.8 MB total) | College profiles | JSON & CSV | Safe for Drive. Zip recommended. |
| `cutoffs/phase3_final_staging/2020-21/` | 326 JSON files | Cutoff records | JSON | Safe for Drive (Zip folder). |
| `cutoffs/phase3_final_staging/2021-22/` | 324 JSON files | Cutoff records | JSON | Safe for Drive (Zip folder). |
| `cutoffs/phase3_final_staging/2022-23/` | 320 JSON files | Cutoff records | JSON | Safe for Drive (Zip folder). |
| `cutoffs/phase3_final_staging/2023-24/` | 332 JSON files | Cutoff records | JSON | Safe for Drive (Zip folder). |
| `cutoffs/phase3_final_staging/2024-25/` | 347 JSON files | Cutoff records | JSON | Safe for Drive (Zip folder). |
| `cutoffs/phase3_final_staging/2025-26/` | 364 JSON files | Cutoff records | JSON | Safe for Drive (Zip folder). |
| `cutoffs/raw_extracted/V4_daataa/` | Extracted raw data | Intermediate staging | Text & JSON | Safe for Drive (Zip folder). |

### 2.3 Vector Database & Embeddings (`vector_index/`)
| File Relative Path | Exact File Size | Record Count | Format | Google Drive Suitability |
|:---|:---:|:---:|:---:|:---|
| `vector_index/chroma.sqlite3` | 6,492,160 bytes (6.19 MB) | 1,041 documents | SQLite / ChromaDB | Safe for Drive. Close SQLite before copy. |
| `vector_index/17a622d2-1429-4290-a42c-01ca86be0c01/` | Chroma segment directory | Index binaries | Chroma segments | Safe for Drive (Zip recommended). |

### 2.4 Model Weights & Artifacts (`model_artifacts/`)
| File Relative Path | Exact File Size | Model / Object Type | Format | Google Drive Suitability |
|:---|:---:|:---:|:---:|:---|
| `model_artifacts/cutoff_regressor_rank.joblib` | 871,976 bytes (851.5 KB) | HistGradientBoosting (Rank) | Joblib binary | Safe for Drive. |
| `model_artifacts/cutoff_regressor_percentile.joblib` | 871,976 bytes (851.5 KB) | HistGradientBoosting (Percentile) | Joblib binary | Safe for Drive. |
| `model_artifacts/label_encoders.joblib` | 32,750 bytes (32.0 KB) | Scikit-learn LabelEncoders | Joblib binary | Safe for Drive. |
| `model_artifacts/tabular_metrics.json` | 602 bytes | Training metrics & R² | JSON | Safe for Drive. |
| `model_artifacts/evaluation_report.json` | 4,399 bytes | Gate evaluation results | JSON | Safe for Drive. |
| `model_artifacts/five_level_test_results.json` | 43,604 bytes | 5-level benchmark responses | JSON | Safe for Drive. |
| `model_artifacts/model_comparison_results.json` | 10,167 bytes | Model comparison metrics | JSON | Safe for Drive. |
| `model_artifacts/lora_adapter/adapter_model.safetensors` | 4,517,152 bytes (4.31 MB) | TinyLlama LoRA weights | Safetensors | Safe for Drive. |
| `model_artifacts/lora_adapter/adapter_config.json` | 1,157 bytes | PEFT LoRA configuration | JSON | Safe for Drive. |
| `model_artifacts/lora_adapter/tokenizer.json` | 3,619,134 bytes (3.45 MB) | Tokenizer definition | JSON | Safe for Drive. |
| `model_artifacts/lora_adapter/training_metrics.json` | 297 bytes | LoRA loss & steps | JSON | Safe for Drive. |
| `model_artifacts/qwen3b_lora_adapter/README.md` | 6,062 bytes | Qwen adapter card | Markdown | Safe for Drive. |

### 2.5 Local Ollama Serving Models (Located in `~/.ollama/models/`)
| Model Identifier | File Size | Base Architecture | Format | Google Drive Suitability |
|:---|:---:|:---:|:---:|:---|
| `qwen2.5-aicon:latest` | 2.4 GB | Qwen2 3B Instruct | GGUF (Q5_K_M) | **Omit from Drive**. Re-pull via Ollama. |
| `qwen2.5:7b` | 4.7 GB | Qwen2 7B Instruct | GGUF (Q4_K_M) | **Omit from Drive**. Re-pull via Ollama. |
| `tinyllama:latest` | 637 MB | TinyLlama 1.1B Chat | GGUF | **Omit from Drive**. Re-pull via Ollama. |

### 2.6 Evaluation Deliverables Package (`AI_CON_Evaluation_Report/`)
| File Relative Path | Exact File Size | Format | Primary Purpose |
|:---|:---:|:---:|:---|
| `AI_CON_Evaluation_Report/AI_CON_Model_Evaluation_Report.pdf` | 66,182 bytes | 22-page PDF | Publication-quality evaluation report. |
| `AI_CON_Evaluation_Report/AI_CON_Model_Evaluation_Report.md` | 60,765 bytes | Markdown | Complete technical report text. |
| `AI_CON_Evaluation_Report/generate_report.py` | 78,112 bytes | Python Script | Standalone report generation engine. |
| `AI_CON_Evaluation_Report/README.md` | 724 bytes | Markdown | Report package manifest & usage. |
| `AI_CON_Evaluation_Report/AI_CON_Evaluation_Report.zip` | 87,854 bytes | ZIP Archive | Self-contained compressed deliverable. |

---

## 3. Directory Exclusion Policy for Google Drive

When sharing or backing up the project, **strictly exclude** the following directories to avoid uploading tens of thousands of duplicate files, platform-specific binaries, or multi-gigabyte models that can be recreated deterministically:

```text
# EXCLUDE from Google Drive / Cloud Sync:
.venv/                                  # 1.5+ GB: Local virtual environment (Windows-specific DLLs)
.venv-test/                             # 800+ MB: Secondary test virtual environment
.cache/                                 # 2.0+ GB: Hugging Face downloaded model weights cache
__pycache__/                            # Compiled Python bytecode (*.pyc)
*.egg-info/                             # Package metadata
.ollama/models/                         # 7.0+ GB: Quantized GGUF blobs (re-download via Ollama CLI)
```
