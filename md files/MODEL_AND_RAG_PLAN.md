# Model, RAG pipeline and agent plan — Admission Evidence Maharashtra

This document answers three questions: which model to train, how the RAG
pipeline should work, and how to structure agents so you can keep adding
tasks without re-architecting later. It also lists exactly what's in this
zip and how to run it.

---

## 1. Which model, and what "training" actually means here

**Short answer: don't train a model to know facts. Use RAG for facts, and
only fine-tune (lightly) for behaviour.** This has been the direction of
every earlier document in this project (AI/ML doc, prompt boilerplate,
anti-hallucination contract) and the recent batches of real scraped data
only reinforce it — you've seen firsthand how easily a wrong fact (a forum
post misread as "established 2008") can slip in. A model that memorised
facts during training can't be corrected without retraining; a RAG system
can be corrected by editing one JSON file.

### What to use as the "guide" model

| Role | Recommendation | Why |
|---|---|---|
| Orchestrator / answer-writer | **Qwen2.5-7B-Instruct** (or 3B if your 8GB VRAM struggles with 7B) | Strong instruction-following, good at structured JSON output and tool-call-style responses, runs locally on your RTX 4060, genuinely good multilingual (Marathi/Hindi) support for later |
| Fallback / comparison | A hosted model (Claude Haiku/Sonnet via API) | Useful during development to compare output quality against your local model, and as a higher-quality option if you ever offer a paid tier |
| Embeddings (for the vector index) | **BAAI/bge-small-en-v1.5** or **sentence-transformers/all-MiniLM-L6-v2** | Small, fast, runs locally, good enough for retrieval over structured/semi-structured college text |

Don't fine-tune anything until you've tried prompting-only first. A 7B
instruct model with a well-written system prompt and the structured
evidence this pipeline hands it will get you further than you'd expect.

### If you do fine-tune — train behaviour, never facts

Fine-tune (QLoRA, via Unsloth) only on:
- **Output format** — always cite `[evidence_id]`, always separate
  VERIFIED_FACT / HISTORICAL_OBSERVATION / MODEL_ESTIMATE / UNKNOWN
- **Abstention** — recognising when evidence is missing and saying so
  instead of guessing (this is the single most valuable behaviour to
  train, given what you've seen the scraper do when it has no good
  evidence)
- **Routing** — given a question, deciding which agent/tool to call
  (see Section 3)

Never fine-tune on raw cutoff numbers, placement figures, or NAAC grades —
those change every year and the model would go stale and confidently
wrong. They always come from RAG retrieval at answer time, not from
weights.

### Training steps (once you have a gold set of ~500-1,000 examples)

1. `python convert_to_training_data.py` (included here) turns your cutoff
   JSONs and college-info JSONs into a chat-format JSONL.
2. Review a random 50-100 examples by hand. This step is not optional —
   automatically generated examples can encode the same extraction bugs
   you've been fixing all week (e.g. a bad `established_year` would
   become a bad training example).
3. Install Unsloth: `pip install unsloth`
4. QLoRA fine-tune (4-bit, rank 16, ~1-2 epochs is usually enough for a
   behaviour-only fine-tune — more risks overfitting the exact phrasing of
   your training examples instead of learning the general behaviour):
   ```python
   from unsloth import FastLanguageModel
   model, tokenizer = FastLanguageModel.from_pretrained(
       "unsloth/Qwen2.5-7B-Instruct-bnb-4bit", max_seq_length=4096, load_in_4bit=True)
   model = FastLanguageModel.get_peft_model(model, r=16, lora_alpha=16,
       target_modules=["q_proj","k_proj","v_proj","o_proj"])
   # then use TRL's SFTTrainer with sft_training_data.jsonl
   ```
5. Evaluate against your held-out gold cases: citation precision/recall,
   abstention accuracy (does it refuse when it should?), and — critically —
   does it ever state a fact that isn't in the evidence you gave it? That
   last one is the real pass/fail gate, more than any fluency metric.

---

## 2. RAG pipeline design

### Why hybrid, not pure vector search

Your own data strategy doc said it already: **semantic similarity alone
is unsafe for cutoffs.** "Civil Engineering GOPENS round 2" and "Civil
Engineering GOPENS round 3" are semantically almost identical but have
different (and non-interchangeable) answers. So:

- **Cutoff/category/round questions → exact structured lookup.** No
  embeddings involved. The college code, branch code, category, and round
  are matched exactly against the hierarchical JSONs you already have.
  This can never return an approximately-right cutoff.
- **College info questions** (placements, NAAC, fees, "tell me about
  X college") **→ vector search** over the scraped `college_info` JSONs,
  since that data is free text and the question phrasing varies a lot.
- **College *name* resolution → vector search first, then exact match.**
  Users won't type the exact official name ("SSGMCE" instead of "Shri Sant
  Gajanan Maharaj College of Engineering,Shegaon"), so name resolution is
  itself a small retrieval problem before either of the above can run.

```
user question
      │
      ▼
 resolve_college()  ── vector search over college names + known
      │                 aliases, falls back to exact/fuzzy string match
      ▼
 classify_intent()  ── rule-based first (keywords), can add an LLM
      │                 classifier later once you have training data
      ▼
   ┌──┴───────────────┐
   ▼                  ▼
cutoff_agent     college_info_agent
(exact JSON       (vector search over
 filter, zero      scraped text, returns
 hallucination     passages + citations)
 risk)
   │                  │
   └────────┬─────────┘
            ▼
   evidence assembled with IDs
            ▼
      LLM writes the final
      answer, citing evidence,
      abstaining if evidence
      is missing or conflicting
```

### Files in this zip that implement this

- `scripts/build_vector_index.py` — builds a local Chroma index over your
  `college_info/*.json` files (one-time step, rerun when you add more
  scraped colleges)
- `scripts/rag_pipeline.py` — the pipeline above, as a single importable
  `answer_question(question)` function plus a CLI you can run directly
- `scripts/agents/` — the agent layer (Section 3)
- `scripts/convert_to_training_data.py` — JSON → fine-tuning JSONL

---

## 3. Agent plan — and a simpler alternative to a full harness

You mentioned wanting to use an agent harness for everything up through
building the college list. Here's my honest take: **a full agent
framework (LangGraph, CrewAI, AutoGen) is worth adopting once your tool
set is stable, not while you're still actively debugging what each tool
should even do** — which is exactly the phase you're in (you've spent this
whole week iterating on what the scraper agent should and shouldn't
trust). A heavy framework adds its own debugging surface on top of yours.

**What I've built instead**: a minimal, dependency-light agent layer —
plain Python classes with a `run(input) -> output` method and a rule-based
orchestrator that routes between them. This gives you the actual thing you
want (separate agents for separate tasks, a model that can guide them) 
without a framework's indirection. It's also a natural stepping stone:
every agent here exposes a plain function signature, so wrapping them as
LangGraph nodes or CrewAI tools later is a small, mechanical change, not a
rewrite.

| Agent | File | Job |
|---|---|---|
| `CutoffAgent` | `agents/cutoff_agent.py` | Exact structured lookup over the hierarchical cutoff JSONs |
| `CollegeInfoAgent` | `agents/college_info_agent.py` | Vector search over scraped college-info JSONs |
| `Orchestrator` | `agents/orchestrator.py` | Resolves the college, classifies intent, calls the right agent(s), hands evidence to the LLM for the final answer |

**Agents to add next**, once this base is solid, in the order I'd build
them:
1. **ComparisonAgent** — takes 2+ college/branch pairs, enforces your own
   "same year/round/metric or `not_comparable`" rule from the product docs
2. **EligibilityAgent** — applies the rule engine (still your biggest
   unbuilt piece, per the original roadmap — this is more valuable than
   more scraping right now)
3. **ConflictAgent** — when the scraper or cutoff data disagrees with
   itself (like the NAAC-grade and established-year conflicts you've
   already seen), surface it instead of letting the orchestrator silently
   pick one
4. **RecommendationAgent** — ranks colleges against a student profile,
   using the tiers (historically compatible / competitive / reach /
   insufficient evidence) from your product architecture doc — build this
   *last*, after the above agents are trustworthy, since it's the one most
   likely to be misread as a promise

---

## 4. How to run everything

Phase 1A uses the v4 sparse dataset (not a `college_info/` scrape folder).
See `README.md` in this folder for the exact PowerShell commands.

```bash
pip install -r requirements.txt
python -m unittest tests.test_phase1a_college_info -v

# College-information index from the v4 dataset (sample first)
python scripts/build_vector_index.py --college-info ../college_ai_consultant_sparse_enriched_v4_no_cutoffs --out ./vector_index --limit 20

# Info-only query: --cutoffs is not required
python scripts/rag_pipeline.py --vector-index ./vector_index \
    --question "What is the affiliation of Government College of Engineering, Amravati?"
```

Cutoff lookup is unchanged when you later have year subfolders from
`extract_cutoffs_hierarchical.py`. Do not pass a fake cutoff directory.

```bash
python scripts/rag_pipeline.py --cutoffs ./out --vector-index ./vector_index \
    --question "What was the GOPENS closing cutoff for Computer Engineering at SSGMCE Shegaon in 2025-26?"

python scripts/convert_to_training_data.py --cutoffs ./out --college-info ../college_ai_consultant_sparse_enriched_v4_no_cutoffs \
    --out ./training/sft_data.jsonl
```

### What's NOT in this zip (and why)

- **No LLM call is wired to a specific provider.** `call_llm()` in
  `rag_pipeline.py` is a small abstraction you fill in — point it at a
  local Ollama server running Qwen2.5, or at Claude's API, or at OpenAI.
  I didn't hardcode one because you'll likely want local inference for
  cost reasons once this is at 700-college scale, but a hosted API for
  development speed first is reasonable too.
- **No actual fine-tuning run.** That needs your real gold-case data and
  a GPU session, neither of which exists in the environment that built
  this zip — Section 1 gives you the exact steps to run yourself.
- **Nothing here was tested against a live vector-store build or LLM
  call**, since this build environment can't reach model-download or
  inference endpoints. The retrieval and filtering *logic* was tested
  against your real JSON structure (see each script's own testing notes),
  but the embedding/LLM-call steps need to be verified on your machine
  first, same as every scraper iteration this week.
