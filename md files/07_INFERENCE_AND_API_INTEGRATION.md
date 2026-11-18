# AI-CON: Inference & API Integration Guide

**Document ID:** AI-CON-INFER-07  
**Serving Engine:** Local Ollama (`http://localhost:11434`) & Python In-Process Pipeline  
**Python Runtime:** `model_rag_agent_plan/.venv`  

---

## 1. Inference Modes Overview

AI-CON supports three distinct inference interfaces depending on the deployment tier:
1. **Multi-Agent Orchestrator API (Python)**: The primary programmatic interface for full query routing, disambiguation, and evidence synthesis.
2. **Deterministic Component APIs (Python)**: Direct access to `CutoffAgent`, `CollegeInfoAgent`, or `HistGradientBoosting` predictors.
3. **Local Ollama REST API (HTTP)**: Serving the conversational model over standard HTTP endpoints (`/api/generate` or `/api/chat`).

---

## 2. Multi-Agent Orchestrator API

The `Orchestrator` is the recommended entrypoint for building chat interfaces, web frontends, or automated agents.

### Complete Python Example:
```python
from scripts.agents.orchestrator import Orchestrator

# Initialize the orchestrator (loads resolvers and agents)
orchestrator = Orchestrator()

# Example 1: Cutoff Query
result = orchestrator.handle_query(
    "What was the GOPENS cutoff for Civil Engineering at Government College of Engineering, Amravati?"
)

print(f"Status: {result.status}")
# Output: Status: answered

print(f"Answer:\n{result.answer}")
# Output: Full grounded answer citing evidence

print(f"Evidence Citations ({len(result.evidence)} found):")
for ev in result.evidence:
    print(f"  - {ev}")
# Output: [2024-25:01002:0100219110:state_level:GOPENS:R1:S1] ...
```

### Handling Ambiguous Queries:
When a query does not uniquely identify a campus, the orchestrator returns `needs_clarification` alongside candidate options:

```python
result = orchestrator.handle_query("What is the cutoff for Government College?")

if result.status == "needs_clarification":
    print("User prompt:", result.message)
    print("Candidate institutions:")
    for c in result.candidates:
        print(f"  • {c}")
```

---

## 3. Direct Deterministic Component APIs

### 3.1 Direct Historical Cutoff Lookup (`CutoffAgent`)
```python
from scripts.agents.cutoff_agent import CutoffAgent

agent = CutoffAgent()
records = agent.query(
    institute_code="01002",
    course_name="Civil Engineering",
    seat_type="GOPENS",
    academic_year="2024-25",
    cap_round=1
)

for r in records:
    print(f"Year: {r['academic_year']} | Round: {r['cap_round']} | "
          f"Closing Rank: {r['closing_rank']} | Percentile: {r['closing_percentile']}")
```

### 3.2 Tabular Predictor Invocation (`HistGradientBoosting`)
To estimate closing ranks and percentiles when historical records are missing:

```python
import joblib
import pandas as pd

# Load saved models and label encoders
rank_model = joblib.load("model_artifacts/cutoff_regressor_rank.joblib")
pct_model = joblib.load("model_artifacts/cutoff_regressor_percentile.joblib")
encoders = joblib.load("model_artifacts/label_encoders.joblib")

# Prepare hypothetical applicant features
sample = pd.DataFrame([{
    "institute_code": encoders["institute_code"].transform(["01002"])[0],
    "course_code": encoders["course_code"].transform(["0100219110"])[0],
    "seat_type": encoders["seat_type"].transform(["GOPENS"])[0],
    "candidature_type": encoders["candidature_type"].transform(["AI to AI"])[0],
    "academic_year": encoders["academic_year"].transform(["2024-25"])[0],
    "cap_round": 1,
    "stage": encoders["stage"].transform(["1"])[0],
}])

pred_rank = int(rank_model.predict(sample)[0])
pred_pct = round(float(pct_model.predict(sample)[0]), 2)

print(f"Predicted Closing Rank: {pred_rank:,}")
print(f"Predicted Closing Percentile: {pred_pct}%")
```

---

## 4. Ollama HTTP REST API Integration

When running AI-CON in production with a decoupled web server (FastAPI, Flask, Next.js), send requests directly to Ollama.

### Verify Ollama Service Status:
```powershell
curl http://localhost:11434/api/tags
```

### POST `/api/generate` (Streaming or Non-Streaming):
```bash
curl -X POST http://localhost:11434/api/generate -d '{
  "model": "qwen2.5-aicon:latest",
  "prompt": "EVIDENCE:\n[2024-25:01002:0100219110:state_level:GOPENS:R1:S1] 2024-25 GCOEA Civil GOPENS closing rank 34240, percentile 88.50\n\nUSER QUERY:\nWhat is the GOPENS cutoff for Civil Engineering at GCOEA?",
  "stream": false,
  "options": {
    "temperature": 0.0,
    "top_p": 0.95
  }
}'
```

### Python Requests Client:
```python
import requests

payload = {
    "model": "qwen2.5-aicon:latest",
    "prompt": "EVIDENCE:\n[MHHEI_00001:profile] GCOEA is Government Autonomous affiliated with SGBAU Amravati.\n\nUSER QUERY:\nIs GCOEA autonomous?",
    "stream": False,
    "options": {"temperature": 0.0}
}

response = requests.post("http://localhost:11434/api/generate", json=payload)
print(response.json()["response"])
```

---

## 5. Loading the TinyLlama LoRA Adapter with Transformers & PEFT

To run inference directly with the fine-tuned PyTorch LoRA adapter:

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base_model_name = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
adapter_dir = "model_artifacts/lora_adapter"

# 1. Load Tokenizer & Base Model
tokenizer = AutoTokenizer.from_pretrained(adapter_dir)
base_model = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    torch_dtype=torch.float32,
    device_map="cpu"
)

# 2. Attach PEFT LoRA Weights
model = PeftModel.from_pretrained(base_model, adapter_dir)
model.eval()

# 3. Format Prompt & Generate
prompt = "<|system|>\nYou are an AI admissions assistant.<|user|>\nWhat are the steps of CAP admissions?<|assistant|>\n"
inputs = tokenizer(prompt, return_tensors="pt")

with torch.no_grad():
    outputs = model.generate(**inputs, max_new_tokens=150, temperature=0.7)

print(tokenizer.decode(outputs[0], skip_special_tokens=True))
```
