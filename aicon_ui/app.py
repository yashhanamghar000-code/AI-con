from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .tinyllama_runtime import generate_grounded_answer, model_status

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
ROOT = Path(os.environ.get("AI_CON_ROOT", PACKAGE_DIR.parent)).expanduser().resolve()

app = FastAPI(
    title="AI-CON Local UI",
    description="Local interface for the existing AI-CON retrieval and admission pipeline.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1600)
    use_llm: bool = False


def _pipeline_candidates() -> list[Path]:
    candidates = [
        ROOT / "model_rag_agent_plan" / "scripts" / "rag_pipeline.py",
        ROOT / "model-rag-agent-plan" / "scripts" / "rag_pipeline.py",
        ROOT / "scripts" / "rag_pipeline.py",
        ROOT / "model_rag_agent_plan" / "rag_pipeline.py",
    ]
    found: list[Path] = []
    for candidate in candidates:
        if candidate.is_file() and candidate not in found:
            found.append(candidate)
    # Fallback for repositories that have moved the pipeline into another folder.
    ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", ".cache"}
    try:
        for candidate in ROOT.rglob("rag_pipeline.py"):
            try:
                rel_parts = candidate.relative_to(ROOT).parts
            except ValueError:
                continue
            if any(part in ignored for part in rel_parts):
                continue
            if candidate.is_file() and candidate not in found:
                found.append(candidate)
            if len(found) >= 5:
                break
    except (OSError, PermissionError):
        pass
    return found


def _pipeline() -> Path | None:
    candidates = _pipeline_candidates()
    return candidates[0] if candidates else None


def _nonempty_dir(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except (OSError, PermissionError):
        return False


def _pipeline_python(pipeline: Path | None) -> Path:
    """Prefer the project's interpreter so its ML dependencies are available."""
    configured = os.environ.get("AI_CON_PYTHON")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return candidate.resolve()
    project_dir = pipeline.parent.parent if pipeline else ROOT
    bases = [project_dir, ROOT, project_dir.parent]
    names = [
        Path(".venv/bin/python"), Path("venv/bin/python"),
        Path(".venv/Scripts/python.exe"), Path("venv/Scripts/python.exe"),
    ]
    for base in bases:
        for rel in names:
            candidate = base / rel
            if candidate.is_file():
                # Do not accidentally select this UI's isolated environment.
                if candidate.resolve() == Path(sys.executable).resolve() and ".venv-ui" in candidate.parts:
                    continue
                return candidate.resolve()
    return Path(sys.executable).resolve()


def _vector_index(pipeline: Path | None) -> Path | None:
    project_dir = pipeline.parent.parent if pipeline else ROOT
    candidates = [
        project_dir / "vector_index",
        project_dir / "vector_index_sample",
        ROOT / "vector_index",
        ROOT / "vector_index_sample",
        ROOT / "model_rag_agent_plan" / "vector_index",
        ROOT / "model_rag_agent_plan" / "vector_index_sample",
    ]
    for path in candidates:
        if _nonempty_dir(path):
            return path.resolve()
    # Locate a persistent Chroma index if the folder has a different name.
    ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", ".cache"}
    try:
        for marker in ROOT.rglob("chroma.sqlite3"):
            if any(part in ignored for part in marker.relative_to(ROOT).parts):
                continue
            if marker.is_file():
                return marker.parent.resolve()
    except (OSError, PermissionError, ValueError):
        pass
    return None


def _cutoff_dir(pipeline: Path | None) -> Path | None:
    project_dir = pipeline.parent.parent if pipeline else ROOT
    candidates = [
        project_dir / "cutoffs" / "phase3_final_staging",
        project_dir / "cutoffs" / "adapted_staging",
        project_dir / "cutoffs",
        ROOT / "cutoffs" / "phase3_final_staging",
        ROOT / "cutoffs" / "adapted_staging",
        ROOT / "cutoffs",
        ROOT / "model_rag_agent_plan" / "cutoffs" / "phase3_final_staging",
        ROOT / "model_rag_agent_plan" / "cutoffs" / "adapted_staging",
        ROOT / "model_rag_agent_plan" / "cutoffs",
    ]
    for path in candidates:
        if _nonempty_dir(path):
            # Avoid passing empty reports/ or historical PDF input folders as cutoff records.
            has_year_folder = any(
                child.is_dir() and len(child.name) == 7 and child.name[4] == "-"
                for child in path.iterdir()
            )
            if has_year_folder or path.name in {"phase3_final_staging", "adapted_staging"}:
                return path.resolve()
    return None


def _status() -> dict[str, Any]:
    pipeline = _pipeline()
    index = _vector_index(pipeline)
    cutoffs = _cutoff_dir(pipeline)
    trained_model = model_status(ROOT)
    ready = pipeline is not None and index is not None
    return {
        "ok": ready,
        "project_root": str(ROOT),
        "pipeline_found": pipeline is not None,
        "pipeline_path": str(pipeline) if pipeline else None,
        "pipeline_working_directory": str(pipeline.parent.parent) if pipeline else None,
        "pipeline_python": str(_pipeline_python(pipeline)) if pipeline else None,
        "vector_index_found": index is not None,
        "vector_index_path": str(index) if index else None,
        "cutoff_data_found": cutoffs is not None,
        "cutoff_data_path": str(cutoffs) if cutoffs else None,
        "trained_model": trained_model,
        "message": (
            "Retrieval pipeline and vector index detected."
            if ready
            else "UI is running, but the existing retrieval pipeline or its vector index was not detected."
        ),
    }


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return _status()


def _norm_key(value: Any) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def _value_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if "value" in value:
            return _value_text(value.get("value"))
        return None
    if isinstance(value, (list, tuple)):
        vals = [_value_text(item) for item in value]
        vals = [v for v in vals if v]
        return ", ".join(vals) if vals else None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "unknown"}:
        return None
    return text


def _pick(mapping: dict[str, Any], *keys: str) -> Any:
    normalized = {_norm_key(k): v for k, v in mapping.items()}
    for key in keys:
        val = normalized.get(_norm_key(key))
        if val not in (None, ""):
            return val
    return None


def _recursive_pick(obj: Any, key_names: set[str], depth: int = 0) -> Any:
    if depth > 5:
        return None
    if isinstance(obj, dict):
        for key, value in obj.items():
            if _norm_key(key) in key_names and value not in (None, ""):
                resolved = _value_text(value)
                if resolved:
                    return resolved
        for value in obj.values():
            found = _recursive_pick(value, key_names, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj[:30]:
            found = _recursive_pick(value, key_names, depth + 1)
            if found:
                return found
    return None


def _record_from_dict(obj: dict[str, Any], source: str) -> dict[str, Any] | None:
    name = _value_text(_pick(obj, "institute_name", "college_name", "institution_name", "name", "college"))
    if not name:
        return None
    # Skip generic metadata records that are not college profiles.
    if name.lower() in {"college dataset index", "dataset manifest", "manifest", "metadata"}:
        return None
    code = _value_text(_pick(obj, "institute_code", "cet_code", "college_code", "code"))
    record_id = _value_text(_pick(obj, "record_id", "id", "college_id"))
    extracted = obj.get("extracted") if isinstance(obj.get("extracted"), dict) else {}
    identity = extracted.get("identity") if isinstance(extracted, dict) and isinstance(extracted.get("identity"), dict) else {}
    district = _value_text(_pick(identity, "district") or _pick(obj, "district")) if isinstance(identity, dict) else _value_text(_pick(obj, "district"))
    city = _value_text(_pick(identity, "city") or _pick(obj, "city")) if isinstance(identity, dict) else _value_text(_pick(obj, "city"))
    kind = _value_text(_pick(obj, "institution_type", "college_type", "type", "ownership"))
    if not kind and isinstance(identity, dict):
        kind = _value_text(_pick(identity, "ownership", "institution_type"))
    affiliation = _recursive_pick(obj, {_norm_key("affiliation")})
    website = _value_text(_pick(obj, "official_website", "website", "url"))
    return {
        "name": name,
        "institute_code": code,
        "record_id": record_id,
        "district": district,
        "city": city,
        "institution_type": kind,
        "affiliation": affiliation,
        "website": website,
        "source_file": source,
    }


def _dataset_roots() -> list[Path]:
    names = [
        "college_ai_consultant_sparse_enriched_v4_no_cutoffs",
        "V4_daataa",
        "V4_dataa",
        "college_info_batch1",
        "NEW_DATA",
        "new_data",
    ]
    return [ROOT / name for name in names if (ROOT / name).is_dir()]


def _load_colleges() -> tuple[list[dict[str, Any]], list[str]]:
    colleges: list[dict[str, Any]] = []
    sources: list[str] = []
    seen: set[tuple[str, str]] = set()

    # Prefer the official CSV index if it exists, without assuming its exact column spelling.
    csv_candidates: list[Path] = []
    for dataset_root in _dataset_roots():
        direct = dataset_root / "college_dataset_index.csv"
        if direct.is_file():
            csv_candidates.append(direct)
        try:
            csv_candidates.extend(p for p in dataset_root.rglob("college_dataset_index.csv") if p.is_file())
        except (OSError, PermissionError):
            pass
    # Some branch layouts keep the index beside the project folder.
    for candidate in [ROOT / "college_dataset_index.csv", ROOT / "model_rag_agent_plan" / "college_dataset_index.csv"]:
        if candidate.is_file():
            csv_candidates.append(candidate)

    for csv_path in dict.fromkeys(csv_candidates):
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    converted = {str(k): v for k, v in row.items() if k is not None}
                    item = _record_from_dict(converted, str(csv_path.relative_to(ROOT)))
                    if item:
                        key = (_norm_key(item["name"]), _norm_key(item.get("institute_code") or ""))
                        if key not in seen:
                            colleges.append(item)
                            seen.add(key)
            sources.append(str(csv_path.relative_to(ROOT)))
        except (OSError, csv.Error, UnicodeError, ValueError):
            continue
        if colleges:
            break

    # Fall back to the actual college JSON records; do not manufacture sample colleges.
    if not colleges:
        for dataset_root in _dataset_roots():
            try:
                files = sorted(dataset_root.rglob("*.json"))
            except (OSError, PermissionError):
                continue
            for path in files[:6000]:
                try:
                    with path.open("r", encoding="utf-8") as handle:
                        obj = json.load(handle)
                except (OSError, json.JSONDecodeError, UnicodeError):
                    continue
                records: list[dict[str, Any]] = []
                if isinstance(obj, dict):
                    item = _record_from_dict(obj, str(path.relative_to(ROOT)))
                    if item:
                        records.append(item)
                    # Handles wrapper objects whose college records are in a list.
                    for key in ("colleges", "records", "items", "data"):
                        inner = obj.get(key)
                        if isinstance(inner, list):
                            records.extend(
                                item for entry in inner if isinstance(entry, dict)
                                if (item := _record_from_dict(entry, str(path.relative_to(ROOT))))
                            )
                elif isinstance(obj, list):
                    records.extend(
                        item for entry in obj if isinstance(entry, dict)
                        if (item := _record_from_dict(entry, str(path.relative_to(ROOT))))
                    )
                for item in records:
                    key = (_norm_key(item["name"]), _norm_key(item.get("institute_code") or ""))
                    if key not in seen:
                        colleges.append(item)
                        seen.add(key)
                if records:
                    sources.append(str(path.relative_to(ROOT)))
    # Keep source metadata compact and avoid leaking absolute paths into the client.
    return colleges, list(dict.fromkeys(sources))[:10]


@lru_cache(maxsize=1)
def _college_cache() -> tuple[list[dict[str, Any]], list[str]]:
    return _load_colleges()


@app.get("/api/colleges")
def colleges(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=60, ge=1, le=150),
) -> dict[str, Any]:
    rows, sources = _college_cache()
    query = _norm_key(q)
    if query:
        rows = [
            row for row in rows
            if query in _norm_key(" ".join(str(row.get(key) or "") for key in ("name", "institute_code", "record_id", "district", "city", "institution_type")))
        ]
    rows = sorted(rows, key=lambda row: _norm_key(row["name"]))[:limit]
    return {
        "count": len(rows),
        "total_loaded": len(_college_cache()[0]),
        "sources": sources,
        "colleges": rows,
        "message": None if rows else "No matching college records were found in the recognized dataset locations.",
    }


def _extract_json(text: str) -> Any | None:
    decoder = json.JSONDecoder()
    # CLI output may have a short log line before the final JSON payload.
    for index in range(len(text) - 1, -1, -1):
        if text[index] == "{":
            try:
                value, _ = decoder.raw_decode(text[index:])
                return value
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    question = payload.question.strip()
    if len(question) < 3:
        raise HTTPException(status_code=422, detail="Please enter a more specific question.")
    state = _status()
    if not state["pipeline_found"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "The existing rag_pipeline.py was not found. The UI is running, but cannot answer until the repository's actual pipeline path is available. "
                f"Checked project root: {ROOT}"
            ),
        )
    if not state["vector_index_found"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "The retrieval pipeline was found, but no non-empty vector index was detected. Build the project index using its README instructions before querying."
            ),
        )

    pipeline = Path(state["pipeline_path"])
    working_dir = pipeline.parent.parent
    command = [
        str(_pipeline_python(pipeline)),
        str(pipeline),
        "--vector-index",
        str(state["vector_index_path"]),
        "--question",
        question,
    ]
    if state["cutoff_data_found"] and state["cutoff_data_path"]:
        command.extend(["--cutoffs", str(state["cutoff_data_path"])])
    if payload.use_llm:
        model_state = state.get("trained_model", {})
        if not model_state.get("available"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "The trained AI-CON TinyLlama adapter is not ready. "
                    + str(model_state.get("message", "Check the adapter files and optional model dependencies."))
                ),
            )
        # Deliberately do not pass --use-llm to rag_pipeline.py: that CLI flag
        # selects the old Ollama/Qwen path. First retrieve evidence, then generate
        # with the saved TinyLlama + LoRA adapter in this long-running UI process.

    environment = os.environ.copy()
    environment.setdefault("PYTHONUNBUFFERED", "1")
    try:
        result = subprocess.run(
            command,
            cwd=str(working_dir),
            env=environment,
            capture_output=True,
            text=True,
            timeout=150,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="The retrieval pipeline exceeded the 150-second request limit. Check model loading and terminal logs.") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not start the existing pipeline: {exc}") from exc

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    parsed = _extract_json(stdout) if stdout else None
    if result.returncode != 0:
        return {
            "status": "pipeline_error",
            "question": question,
            "return_code": result.returncode,
            "message": "The existing pipeline returned a non-zero exit code. See details below.",
            "stdout": stdout[-6000:],
            "stderr": stderr[-6000:],
        }
    if parsed is not None:
        if payload.use_llm and isinstance(parsed, dict):
            pipeline_status = str(parsed.get("status", ""))
            evidence = str(parsed.get("evidence", "") or "")
            # Do not ask a language model to fill data gaps or turn an unresolved
            # college/cutoff query into a fabricated answer.
            blocked_statuses = {"needs_clarification", "unavailable", "pipeline_error", "llm_error"}
            evidence_index_missing = (
                "College-information index is not available" in evidence
                and not any(tag in evidence for tag in ("[MHHEI_", "[EV-", "[20"))
            )
            if pipeline_status not in blocked_statuses and evidence.strip() and not evidence_index_missing:
                try:
                    parsed["answer"] = generate_grounded_answer(question, evidence, root=ROOT)
                    parsed["status"] = "answered"
                    parsed["model"] = "TinyLlama 1.1B Chat + AI-CON LoRA adapter"
                    parsed["inference_backend"] = "Transformers + PEFT"
                except Exception as exc:
                    # Preserve evidence and make inference failure explicit.
                    parsed["status"] = "model_error"
                    parsed["message"] = (
                        "Evidence was retrieved, but the trained AI-CON model could not generate an answer. "
                        f"Details: {type(exc).__name__}: {exc}"
                    )
            else:
                parsed["model_skipped_reason"] = (
                    "No safe, sufficiently grounded evidence was available for generation; "
                    "the structured retrieval result is shown instead."
                )
        return {"status": "ok", "question": question, "result": parsed, "stderr": stderr[-3000:] if stderr else None}
    return {
        "status": "unparsed_output",
        "question": question,
        "message": "The pipeline ran, but its output was not valid JSON. Raw output is preserved for debugging.",
        "stdout": stdout[-8000:],
        "stderr": stderr[-3000:] if stderr else None,
    }
