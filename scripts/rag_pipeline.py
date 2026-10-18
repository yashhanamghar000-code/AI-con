#!/usr/bin/env python3
"""
Single entry point for the AI-con retrieval pipeline.
Wires CutoffAgent + CollegeInfoAgent + Orchestrator together and exposes:
  answer_question(question, ...)
plus a CLI for testing.

College-information only (Phase 1, no cutoff dataset required):
    python scripts/rag_pipeline.py --vector-index ./vector_index \\
        --question "What is the affiliation of Government College of Engineering, Amravati?"

With cutoffs (when a hierarchical cutoff folder exists in later phases):
    python scripts/rag_pipeline.py --cutoffs ./out --vector-index ./vector_index \\
        --question "What was the GOPENS cutoff for Computer Engineering at ... in 2025-26?"

Without an LLM wired up, it returns the raw structured retrieved evidence
instead of a written answer.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Add scripts and scripts/agents to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent
AGENTS_DIR = SCRIPTS_DIR / "agents"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from cutoff_agent import CutoffAgent  # noqa: E402
from orchestrator import Orchestrator  # noqa: E402

try:
    from college_info_agent import CollegeInfoAgent
except Exception:
    CollegeInfoAgent = None  # chromadb/sentence-transformers not installed yet


def call_llm(
    system: str,
    user: str,
    model: str = "qwen2.5:7b",
    host: str = "http://localhost:11434",
    timeout: float = 60.0,
) -> str:
    """Call the local Ollama daemon for grounded text generation."""
    try:
        from ollama_client import call_ollama
    except ImportError:
        from scripts.ollama_client import call_ollama
    return call_ollama(
        system=system,
        user=user,
        model=model,
        host=host,
        timeout=timeout,
        temperature=0.0,
    )


def build_pipeline(
    cutoffs_dir: Optional[str] = None,
    vector_index_dir: Optional[str] = None,
    use_llm: bool = False,
    embedding_function: Any = None,
    ollama_model: str = "qwen2.5:7b",
    ollama_host: str = "http://localhost:11434",
    llm_call: Optional[Callable[[str, str], str]] = None,
) -> Orchestrator:
    cutoff_agent = None
    if cutoffs_dir:
        cutoffs_path = Path(cutoffs_dir)
        if not cutoffs_path.is_dir():
            raise SystemExit(
                f"Cutoff directory not found: {cutoffs_path}\n"
                "Omit --cutoffs to run college-information questions only."
            )
        cutoff_agent = CutoffAgent(cutoffs_dir)

    info_agent = None
    if vector_index_dir:
        if CollegeInfoAgent is None:
            print(
                "warning: college info agent unavailable "
                "(install chromadb and sentence-transformers); "
                "cutoff-only mode if --cutoffs was provided"
            )
        else:
            try:
                info_agent = CollegeInfoAgent(
                    vector_index_dir, embedding_function=embedding_function
                )
            except SystemExit as e:
                print(f"warning: college info agent unavailable ({e}); cutoff-only mode")

    if cutoff_agent is None and info_agent is None:
        raise SystemExit(
            "Nothing to search. For college information, build an index and pass --vector-index:\n"
            "  python scripts/build_vector_index.py "
            "--college-info ../college_ai_consultant_sparse_enriched_v4_no_cutoffs "
            "--out ./vector_index --limit 20\n"
            '  python scripts/rag_pipeline.py --vector-index ./vector_index '
            '--question "What is the affiliation of Government College of Engineering, Amravati?"\n'
            "A cutoff directory is optional and must not be invented if missing."
        )

    if llm_call is not None:
        llm = llm_call
    elif use_llm:
        llm = lambda sys_p, usr_p: call_llm(
            sys_p, usr_p, model=ollama_model, host=ollama_host
        )
    else:
        llm = None
    return Orchestrator(cutoff_agent, info_agent, llm_call=llm)


def answer_question(
    question: str,
    cutoffs_dir: Optional[str] = None,
    vector_index_dir: Optional[str] = None,
    institute_hint: Optional[str] = None,
    use_llm: bool = False,
    embedding_function: Any = None,
    ollama_model: str = "qwen2.5:7b",
    ollama_host: str = "http://localhost:11434",
    llm_call: Optional[Callable[[str, str], str]] = None,
) -> Dict[str, Any]:
    orch = build_pipeline(
        cutoffs_dir=cutoffs_dir,
        vector_index_dir=vector_index_dir,
        use_llm=use_llm,
        embedding_function=embedding_function,
        ollama_model=ollama_model,
        ollama_host=ollama_host,
        llm_call=llm_call,
    )
    return orch.answer(question, institute_hint=institute_hint)


def main():
    ap = argparse.ArgumentParser(description="AI-con Phase 2 Local LLM + RAG Retrieval Pipeline")
    ap.add_argument(
        "--cutoffs",
        default=None,
        help="Hierarchical cutoff JSON folder (year subfolders). Optional for info-only queries.",
    )
    ap.add_argument(
        "--vector-index",
        default=None,
        help="Chroma index from build_vector_index.py. Required for college-information queries.",
    )
    ap.add_argument("--question", required=True, help="Student admission or college query")
    ap.add_argument(
        "--college",
        default=None,
        help="Explicit college hint if question doesn't name the college clearly",
    )
    ap.add_argument(
        "--use-llm",
        action="store_true",
        help="Call local Ollama LLM for written answer from evidence",
    )
    ap.add_argument(
        "--ollama-model",
        default="qwen2.5:7b",
        help="Local Ollama model name (default: qwen2.5:7b)",
    )
    ap.add_argument(
        "--ollama-host",
        default="http://localhost:11434",
        help="Local Ollama daemon host URL (default: http://localhost:11434)",
    )
    args = ap.parse_args()

    result = answer_question(
        args.question,
        args.cutoffs,
        args.vector_index,
        institute_hint=args.college,
        use_llm=args.use_llm,
        ollama_model=args.ollama_model,
        ollama_host=args.ollama_host,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
