#!/usr/bin/env python3
"""
AI-CON System Diagnostics Tool (Task 1)
Reports component availability, dataset paths, vector index stats,
and ML model status safely without exposing secrets.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CUTOFFS_DIR = PROJECT_ROOT / "cutoffs" / "phase3_final_staging"
VECTOR_INDEX_DIR = PROJECT_ROOT / "vector_index"
MODEL_ARTIFACTS_DIR = PROJECT_ROOT / "model_artifacts"
TRAINING_DATA_DIR = PROJECT_ROOT / "training_data"


def run_diagnostics() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "status": "ok",
        "python_version": sys.version.split()[0],
        "project_root": str(PROJECT_ROOT),
        "components": {},
    }

    # 1. Cutoffs Dataset
    cutoffs_found = CUTOFFS_DIR.exists() and any(CUTOFFS_DIR.iterdir())
    cutoffs_info = {
        "configured_path": str(CUTOFFS_DIR),
        "available": cutoffs_found,
        "institutes_loaded": 0,
        "total_files": 0,
    }
    if cutoffs_found:
        files = list(CUTOFFS_DIR.rglob("*.json"))
        cutoffs_info["total_files"] = len(files)
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
            sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "agents"))
            from cutoff_agent import CutoffAgent
            agent = CutoffAgent(str(CUTOFFS_DIR))
            cutoffs_info["institutes_loaded"] = len(agent._by_code)
        except Exception as e:
            cutoffs_info["error"] = str(e)
    report["components"]["cutoffs"] = cutoffs_info

    # 2. Vector Index (ChromaDB)
    vector_found = VECTOR_INDEX_DIR.exists() and (VECTOR_INDEX_DIR / "chroma.sqlite3").exists()
    vector_info = {
        "configured_path": str(VECTOR_INDEX_DIR),
        "available": vector_found,
        "total_documents": 0,
        "collections": [],
    }
    if vector_found:
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(VECTOR_INDEX_DIR))
            collections = [c.name for c in client.list_collections()]
            vector_info["collections"] = collections
            if "college_info" in collections:
                col = client.get_collection("college_info")
                vector_info["total_documents"] = col.count()
        except Exception as e:
            vector_info["error"] = str(e)
    report["components"]["vector_index"] = vector_info

    # 3. Tabular ML Models & Encoders
    rank_p = MODEL_ARTIFACTS_DIR / "cutoff_regressor_rank.joblib"
    pct_p = MODEL_ARTIFACTS_DIR / "cutoff_regressor_percentile.joblib"
    enc_p = MODEL_ARTIFACTS_DIR / "label_encoders.joblib"
    ml_info = {
        "configured_path": str(MODEL_ARTIFACTS_DIR),
        "rank_model_present": rank_p.exists(),
        "percentile_model_present": pct_p.exists(),
        "label_encoders_present": enc_p.exists(),
        "ready": rank_p.exists() and pct_p.exists() and enc_p.exists(),
    }
    report["components"]["tabular_ml"] = ml_info

    # 4. Training Data
    features_csv = TRAINING_DATA_DIR / "cutoff_tabular_features.csv"
    train_data_info = {
        "configured_path": str(TRAINING_DATA_DIR),
        "tabular_features_present": features_csv.exists(),
        "file_size_bytes": features_csv.stat().st_size if features_csv.exists() else 0,
    }
    report["components"]["training_data"] = train_data_info

    # 5. LLM / Orchestrator Configuration
    report["components"]["orchestrator"] = {
        "default_ollama_model": "qwen2.5:7b",
        "default_embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    }

    return report


if __name__ == "__main__":
    rep = run_diagnostics()
    print(json.dumps(rep, indent=2))
