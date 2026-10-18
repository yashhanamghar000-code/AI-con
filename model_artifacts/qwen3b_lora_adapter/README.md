---
language:
- en
- mr
license: apache-2.0
base_model: Qwen/Qwen2.5-Coder-3B-Instruct
tags:
- lora
- peft
- text-generation
- maharashtra-cet
- mht-cet
- admissions-counselling
- higher-education
- rag
pipeline_tag: text-generation
---

# AI-CON: Qwen 2.5 3B Conversational Admissions Counselling LoRA

**AI-CON** is a specialized decision-support system for Maharashtra engineering college admissions governed by the State Common Entrance Test Cell (MHT-CET Centralized Admission Process - CAP).

This repository contains the fine-tuned **PEFT LoRA adapter** trained on top of [`Qwen/Qwen2.5-Coder-3B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct) for grounded conversational counselling, strict evidence citation adherence, transparent abstention, and anti-hallucination.

---

## Model Details

- **Base Model**: [`Qwen/Qwen2.5-Coder-3B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct)
- **Base Architecture**: Qwen2 (36 transformer layers, 2048 hidden dimension, 16 attention heads, 2 KV heads, 151,936 vocab size)
- **Adapter Type**: PEFT Low-Rank Adaptation (LoRA)
- **LoRA Hyperparameters**:
  - Rank ($r$): `8`
  - Alpha ($\alpha$): `16`
  - Dropout: `0.05`
  - Target Modules: `["q_proj", "k_proj", "v_proj", "o_proj"]`
  - Trainable Parameters: `409,600` (0.066% parameter overhead)
- **Precision**: 32-bit Float / 16-bit BFloat compatible
- **Chat Template**: ChatML format (`<|im_start|>` and `<|im_end|>`)
- **License**: Apache 2.0

---

## Intended Use

This conversational model acts as Component 4 of the 4-tier AI-CON admissions pipeline:
1. **CutoffAgent**: Structured exact historical cutoff lookup across 181,137 official cutoff records.
2. **CollegeInfoAgent**: ChromaDB vector index over 1,041 accredited Maharashtra college profiles.
3. **Tabular Predictor**: Trained `HistGradientBoostingRegressor` models predicting expected closing ranks ($R^2 = 0.571$) and percentiles ($R^2 = 0.526$).
4. **LLM Counselling Assistant (This Model)**: Explains retrieved evidence in student-friendly terms, cites exact bracketed evidence identifiers (e.g. `[2024-25:01002:0100219110:state_level:GOPENS:R1:S1]`), asks for clarification on ambiguous college names, and strictly abstains when courses are unoffered.

### Primary Use Cases:
- Explaining MHT-CET CAP round allocation rules and eligibility criteria.
- Interpreting historical cutoff trends across academic years (2020-21 through 2025-26).
- Answering qualitative inquiries regarding college affiliation, autonomy, NAAC/NBA accreditation, and district locations.
- Advising on preference list structuring (reach, realistic, and safe option tiers).

### Out-of-Scope & Limitations:
- **Never promise admission**: MHT-CET admissions depend dynamically on seat matrix variations, candidate reservation categories, and annual applicant percentiles.
- **Do not bypass deterministic lookup**: The model must never invent, guess, or extrapolate numeric cutoffs without structured retrieval evidence.

---

## Training Dataset

The conversational fine-tuning dataset is constructed from verified, official Directorate of Technical Education (DTE) Maharashtra and State CET Cell published documents:
- **Historical Cutoff Observations**: 181,137 records spanning 6 academic years (`2020-21`, `2021-22`, `2022-23`, `2023-24`, `2024-25`, `2025-26`).
- **College Directory Profiles**: 1,041 institution profiles with official DTE 4-digit / 5-digit codes.
- **Conversational SFT Examples**: 12,041 high-quality multi-turn dialogues formatted in ChatML:
  - Training split (`train.jsonl`): 10,836 dialogues
  - Validation split (`val.jsonl`): 1,205 dialogues

---

## Evaluation Benchmark Summary

| Evaluation Category | Benchmark Target | Result | Status |
|:---|:---|:---|:---:|
| **Exact Cutoff Retrieval** | Zero-guess accuracy against verified 2024-25 GCOE Amravati GOPENS cutoff (Rank: 34,240, Pct: 85.58%) | 100% exact numerical match | **PASS** |
| **Qualitative Information** | Accuracy on affiliation (Sant Gadge Baba Amravati Univ) & autonomy status | 100% factual match | **PASS** |
| **Abstention Gate** | Strict refusal on unoffered disciplines (e.g. Aerospace Engg at Indala College) | Status: `unavailable`, zero hallucinated numbers | **PASS** |
| **Ambiguity Resolution** | Detection of ambiguous query "Government College" | Status: `needs_clarification`, 4+ candidates surfaced | **PASS** |
| **Citation Compliance** | Verbatim bracketed provenance tag `[2024-25:01002:...]` | Exact identifier preserved | **PASS** |

---

## Quickstart & Usage

```python
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base_model_id = "Qwen/Qwen2.5-Coder-3B-Instruct"
adapter_id = "yashhanamghar9099/AI-CON-Qwen2.5-3B"

tokenizer = AutoTokenizer.from_pretrained(base_model_id)
base_model = AutoModelForCausalLM.from_pretrained(
    base_model_id,
    torch_dtype=torch.bfloat16,
    device_map="auto"
)
model = PeftModel.from_pretrained(base_model, adapter_id)

messages = [
    {
        "role": "system",
        "content": (
            "You are an admission decision-support assistant for Maharashtra engineering colleges. "
            "Use only supplied evidence. Cite evidence IDs in [brackets]. Never promise admission."
        )
    },
    {
        "role": "user",
        "content": "What was the GOPENS cutoff for Civil Engineering at GCOE Amravati in 2024-25?"
    }
]

inputs = tokenizer.apply_chat_template(messages, tokenize=True, return_tensors="pt").to(model.device)
outputs = model.generate(inputs, max_new_tokens=200, do_sample=False)
print(tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True))
```

---

## Redistribution & License Compliance

- **Upstream License**: Apache 2.0 (Alibaba Cloud Qwen 2.5 series).
- **Private Data Protection**: No private source code, raw personal student data, or sensitive API credentials are included in this model repository.
- **Redistribution Permission**: Permitted under Apache 2.0 with proper attribution and copyright notices.
