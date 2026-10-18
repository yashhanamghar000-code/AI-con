#!/usr/bin/env python3
"""
Build a local persistent vector index over college JSON files for the
semantic-search half of the RAG pipeline (identity, affiliation, location, sources).

Supports the v4 sparse dataset in college_ai_consultant_sparse_enriched_v4_no_cutoffs/
as well as the older scraped shape (flat extracted fields, placement_mentions,
raw_text_pages) when those fields are actually present.

Uses the reusable CollegeRecord adapter (scripts/college_adapter.py).
Cutoff numbers are NEVER indexed here.

Setup:
    pip install chromadb sentence-transformers

Run (from model_rag_agent_plan/):
    python scripts/build_vector_index.py --college-info ../college_ai_consultant_sparse_enriched_v4_no_cutoffs --out ./vector_index --limit 20
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Enable relative import from scripts/ or root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from college_adapter import (
    IDENTITY_VALUE_FIELDS,
    CollegeRecord,
    adapt_college_record,
    factual_value,
    is_college_record,
    sanitize_chroma_metadata as chroma_safe_metadata,
)

SKIP_FILENAMES = {"dataset_manifest.json"}


def chunk_text(text: str, size: int = 1500, overlap: int = 150) -> List[str]:
    """Split long unstructured text into overlapping chunks."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += size - overlap
    return chunks


def _stable_id(college_json: Dict[str, Any]) -> str:
    """Generate stable ID from record_id, institute_code, or sanitized institute_name."""
    record_id = factual_value(college_json.get("record_id"))
    if record_id:
        return str(record_id)
    code = factual_value(college_json.get("institute_code"))
    if code:
        return str(code)
    name = factual_value(college_json.get("institute_name")) or "unknown"
    return re.sub(r"[^A-Za-z0-9]+", "_", str(name)).strip("_") or "unknown"


def extract_profile_facts(college_json: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Plain-text facts actually present on a v4 (or legacy) college record."""
    record = adapt_college_record(college_json)
    if record is None:
        return []

    facts: List[Tuple[str, str]] = []
    if record.institute_name:
        facts.append(("institute_name", record.institute_name))
    if record.institute_code:
        facts.append(("institute_code", record.institute_code))
    if record.record_id:
        facts.append(("record_id", record.record_id))
    if record.official_website:
        facts.append(("official_website", record.official_website))
    if record.institution_type:
        facts.append(("institution_type", record.institution_type))

    for field in IDENTITY_VALUE_FIELDS:
        if field in record.raw_facts and not any(k == field for k, _ in facts):
            facts.append((field, record.raw_facts[field]))

    if record.sources_consulted:
        facts.append(("sources_consulted", "; ".join(record.sources_consulted)))

    return facts


def build_college_documents(college_json: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Returns a list of (doc_id, text, metadata) tuples for one college."""
    record = adapt_college_record(college_json)
    if record is None:
        return []

    stable = record.stable_id
    base_meta = record.get_chroma_metadata(chunk_type="profile")

    docs: List[Tuple[str, str, Dict[str, Any]]] = []

    # 1. Profile document (factual properties)
    profile_text = record.get_profile_text()
    if profile_text and profile_text.strip():
        docs.append((f"{stable}_profile", profile_text, dict(base_meta)))

    # 2. Placement mentions (legacy/scraped records)
    for i, pm in enumerate(record.placement_mentions):
        text = f"{record.institute_name} placement mention: {pm.value}"
        if pm.kind:
            text += f" ({pm.kind})"
        if pm.context:
            text += f". Context: {pm.context}"
        meta = record.get_chroma_metadata(chunk_type="placement")
        if pm.source:
            meta["source_page"] = pm.source
        docs.append((f"{stable}_placement_{i}", text, meta))

    # 3. Raw text pages (legacy/scraped records)
    for url, text in record.raw_text_pages.items():
        for j, chunk in enumerate(chunk_text(text)):
            meta = record.get_chroma_metadata(chunk_type="raw_page")
            meta["source_page"] = url
            doc_text = f"{record.institute_name}: {chunk}" if record.institute_name else chunk
            docs.append((f"{stable}_page_{abs(hash(url)) % 100000}_{j}", doc_text, meta))

    return docs


def iter_college_files(college_info_dir: Path, limit: int = 0) -> List[Path]:
    """Collect valid college JSON paths in sorted order."""
    files: List[Path] = []
    for path in sorted(Path(college_info_dir).glob("*.json")):
        if path.name.startswith("_") or path.name in SKIP_FILENAMES:
            continue
        files.append(path)
    if limit:
        files = files[:limit]
    return files


def ensure_chroma_embedding_function(ef: Any) -> Any:
    """Ensure a custom embedding function satisfies ChromaDB's EmbeddingFunction protocol."""
    if ef is None:
        return None
    if not hasattr(ef, "name"):
        name_str = getattr(ef, "__class__").__name__.lower()
        setattr(ef, "name", lambda: name_str)
    if not hasattr(ef, "default_space"):
        setattr(ef, "default_space", lambda: "cosine")
    if not hasattr(ef, "supported_spaces"):
        setattr(ef, "supported_spaces", lambda: ["cosine", "l2", "ip"])
    if not hasattr(ef, "get_config"):
        setattr(ef, "get_config", lambda: {})
    if not hasattr(ef, "build_from_config"):
        setattr(ef, "build_from_config", lambda cfg: ef)
    return ef


def index_college_files(
    college_info_dir: Union[str, Path],
    out_dir: Union[str, Path],
    model: str = "sentence-transformers/all-MiniLM-L6-v2",
    limit: int = 0,
    embedding_function: Any = None,
    rebuild: bool = False,
) -> Dict[str, int]:
    """Index college records into a persistent Chroma collection."""
    try:
        import chromadb
    except ImportError:
        raise SystemExit(
            "Missing dependency: chromadb (and sentence-transformers for the default embedder).\n"
            "From the model_rag_agent_plan folder run:\n"
            "  pip install -r requirements.txt"
        )

    if embedding_function is not None:
        embedding_function = ensure_chroma_embedding_function(embedding_function)
    else:
        try:
            from chromadb.utils import embedding_functions
            embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model)
        except ImportError:
            raise SystemExit(
                "Missing dependency: sentence-transformers.\n"
                "From the model_rag_agent_plan folder run:\n"
                "  pip install -r requirements.txt"
            )

    college_info_dir = Path(college_info_dir)
    if not college_info_dir.is_dir():
        raise SystemExit(f"College-info directory not found: {college_info_dir}")

    out_path = Path(out_dir)
    if rebuild and out_path.exists():
        print(f"Rebuilding index: clearing existing directory {out_path}...")
        shutil.rmtree(out_path, ignore_errors=True)

    out_path.mkdir(parents=True, exist_ok=True)

    try:
        client = chromadb.PersistentClient(path=str(out_path))
        collection = client.get_or_create_collection("college_info", embedding_function=embedding_function)
    except Exception as exc:
        raise SystemExit(
            f"Failed to initialize Chroma persistent index at {out_path}: {exc}\n"
            "If the index was created with an incompatible schema or corrupted, run with --rebuild."
        )

    files = iter_college_files(college_info_dir, limit=limit)
    total_docs, skipped, indexed_colleges = 0, 0, 0

    for path in files:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Warning: skipped {path.name} (invalid JSON: {exc})")
            skipped += 1
            continue

        if not is_college_record(record):
            skipped += 1
            continue

        docs = build_college_documents(record)
        if not docs:
            skipped += 1
            continue

        try:
            collection.upsert(
                ids=[d[0] for d in docs],
                documents=[d[1] for d in docs],
                metadatas=[d[2] for d in docs],
            )
            total_docs += len(docs)
            indexed_colleges += 1
        except Exception as exc:
            print(f"Warning: failed to index documents from {path.name}: {exc}")
            skipped += 1

    print(
        f"Indexed {total_docs} chunks from {indexed_colleges} colleges "
        f"({skipped} skipped) into {out_dir}"
    )
    return {"chunks": total_docs, "colleges": indexed_colleges, "skipped": skipped}


def main():
    ap = argparse.ArgumentParser(description="Build Chroma vector index for college information")
    ap.add_argument(
        "--college-info",
        default=None,
        help="Folder of per-college JSON files (v4 dataset or legacy college_info)",
    )
    ap.add_argument("--out", default="./vector_index", help="Directory for the Chroma persistent index")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Index only the first N college JSON files (0 = all, e.g. 20 for sample mode)",
    )
    ap.add_argument(
        "--rebuild",
        action="store_true",
        help="Wipe and recreate index directory cleanly before indexing",
    )
    args = ap.parse_args()

    college_info_path = args.college_info
    if not college_info_path:
        for candidate in ("cutoffs/college_ai_consultant_sparse_enriched_v4_no_cutoffs", "../college_ai_consultant_sparse_enriched_v4_no_cutoffs"):
            if Path(candidate).is_dir():
                college_info_path = candidate
                break
    if not college_info_path or not Path(college_info_path).is_dir():
        raise SystemExit(f"College info directory not found: {college_info_path}")

    index_college_files(
        college_info_path,
        args.out,
        model=args.model,
        limit=args.limit,
        rebuild=args.rebuild,
    )


if __name__ == "__main__":
    main()
