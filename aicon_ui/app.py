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

import asyncio
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .tinyllama_runtime import generate_grounded_answer, model_status

# Import strategic and scaling services
try:
    from scripts.cache_service import get_cache_service
    from scripts.cap_strategy_service import CAPStrategyService
    from scripts.college_comparison_service import CollegeComparisonService
except ImportError:
    try:
        from cache_service import get_cache_service
        from cap_strategy_service import CAPStrategyService
        from college_comparison_service import CollegeComparisonService
    except ImportError:
        get_cache_service = None
        CAPStrategyService = None
        CollegeComparisonService = None

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
    session_id: Optional[str] = None
    profile: Optional[dict[str, Any]] = None


class ProfileRequest(BaseModel):
    session_id: str = "default_session"
    percentile: Optional[float] = None
    merit_rank: Optional[int] = None
    category: str = "GOPENS"
    home_university: str = "SPPU"
    preferred_location: str = "Pune"
    preferred_branches: list[str] = Field(default_factory=lambda: ["Computer Engineering"])


class CompareRequest(BaseModel):
    institute_codes: list[str] = Field(min_length=2, max_length=3)
    branch: str = "Computer Engineering"
    category: str = "GOPENS"
    student_percentile: Optional[float] = None
    academic_year: str = "2024-25"


class OptionFormValidateRequest(BaseModel):
    choices: list[dict[str, Any]]
    student_profile: Optional[dict[str, Any]] = None


class FreezeFloatRequest(BaseModel):
    allotted_choice_no: int
    allotted_choice_code: str = ""
    allotted_institute_name: str
    cap_round: int = 1
    student_percentile: float
    category: str = "GOPENS"
    higher_choices: list[dict[str, Any]] = Field(default_factory=list)


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
    try:
        from interactive_terminal import get_engine
        engine = get_engine()
        cutoffs_ok = engine.cutoff_agent is not None
        vector_ok = engine.info_agent is not None
    except Exception:
        cutoffs_ok = _cutoff_dir(None) is not None
        vector_ok = _vector_index(None) is not None

    trained_model = model_status(ROOT)
    ready = cutoffs_ok or vector_ok
    return {
        "ok": ready,
        "project_root": str(ROOT),
        "pipeline_found": True,
        "pipeline_path": str(ROOT / "interactive_terminal.py"),
        "pipeline_working_directory": str(ROOT),
        "pipeline_python": str(sys.executable),
        "vector_index_found": vector_ok,
        "vector_index_path": str(ROOT / "vector_index") if vector_ok else None,
        "cutoff_data_found": cutoffs_ok,
        "cutoff_data_path": str(ROOT / "cutoffs" / "phase3_final_staging") if cutoffs_ok else None,
        "trained_model": trained_model,
        "message": (
            "Interactive Orchestrator engine and data stores connected."
            if ready
            else "UI is running, but cutoff or vector data stores were not detected."
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
    candidates = [
        ROOT / "cutoffs" / "college_ai_consultant_sparse_enriched_v4_no_cutoffs",
        ROOT / "college_ai_consultant_sparse_enriched_v4_no_cutoffs",
        ROOT / "V4_daataa",
        ROOT / "V4_dataa",
        ROOT / "college_info_batch1",
        ROOT / "NEW_DATA",
        ROOT / "new_data",
    ]
    return [p for p in candidates if p.is_dir()]


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


@app.post("/api/profile")
def save_profile(payload: ProfileRequest) -> dict[str, Any]:
    if get_cache_service:
        cache = get_cache_service()
        cache.cache_session(payload.session_id, payload.model_dump())

    # Sync into running engine if available
    try:
        from interactive_terminal import get_engine
        engine = get_engine()
        if engine.orch is not None:
            engine.orch._conv_context.update({
                "percentile": payload.percentile,
                "rank": payload.merit_rank,
                "category": payload.category,
                "location": payload.preferred_location,
                "preferred_branches": payload.preferred_branches,
            })
    except Exception:
        pass

    return {"status": "ok", "session_id": payload.session_id, "profile": payload.model_dump()}


@app.get("/api/profile")
def get_profile(session_id: str = Query(default="default_session")) -> dict[str, Any]:
    profile = None
    if get_cache_service:
        cache = get_cache_service()
        profile = cache.get_cached_session(session_id)

    if not profile:
        profile = {
            "session_id": session_id,
            "percentile": 94.0,
            "merit_rank": None,
            "category": "GOPENS",
            "home_university": "SPPU",
            "preferred_location": "Pune",
            "preferred_branches": ["Computer Engineering"],
        }
    return {"status": "ok", "session_id": session_id, "profile": profile}


@app.post("/api/compare")
def compare_colleges_endpoint(payload: CompareRequest) -> dict[str, Any]:
    try:
        from interactive_terminal import get_engine
        engine = get_engine()
        c_agent = engine.cutoff_agent
    except Exception:
        c_agent = None

    if CollegeComparisonService:
        service = CollegeComparisonService(cutoff_agent=c_agent)
        return service.compare(
            institute_codes=payload.institute_codes,
            branch=payload.branch,
            category=payload.category,
            student_percentile=payload.student_percentile,
            academic_year=payload.academic_year,
        )
    return {"error": "CollegeComparisonService unavailable."}


@app.post("/api/option-form/validate")
def validate_option_form_endpoint(payload: OptionFormValidateRequest) -> dict[str, Any]:
    if CAPStrategyService:
        return CAPStrategyService.validate_option_form(payload.choices, payload.student_profile)
    return {"valid": True, "risk_level": "unknown", "message": "CAPStrategyService unavailable."}


@app.post("/api/option-form/export-csv")
def export_option_form_csv(payload: OptionFormValidateRequest) -> Response:
    if CAPStrategyService:
        csv_text = CAPStrategyService.export_dte_csv(payload.choices)
    else:
        csv_text = "Preference_Number,Choice_Code,Institute_Code,Institute_Name,Course_Branch_Name,Category,Historical_Cutoff_Percentile,Feasibility_Tier\n"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=aicon_cap_option_form.csv"},
    )


@app.post("/api/strategy/freeze-float")
def freeze_float_endpoint(payload: FreezeFloatRequest) -> dict[str, Any]:
    if CAPStrategyService:
        return CAPStrategyService.analyze_freeze_float(
            allotted_choice_no=payload.allotted_choice_no,
            allotted_choice_code=payload.allotted_choice_code,
            allotted_institute_name=payload.allotted_institute_name,
            cap_round=payload.cap_round,
            student_percentile=payload.student_percentile,
            category=payload.category,
            higher_choices=payload.higher_choices,
        )
    return {"decision": "FREEZE", "headline": "CAPStrategyService unavailable"}


@app.get("/api/documents/checklist")
def document_checklist_endpoint(
    category: str = Query(default="OPEN"),
    tfws: bool = Query(default=False),
    ews: bool = Query(default=False),
    pwd: bool = Query(default=False),
    defense: bool = Query(default=False),
    income: Optional[float] = Query(default=None),
) -> dict[str, Any]:
    if CAPStrategyService:
        return CAPStrategyService.get_document_checklist(
            category=category,
            has_tfws=tfws,
            has_ews=ews,
            has_pwd=pwd,
            has_def=defense,
            annual_income=income,
        )
    return {"category": category, "common_documents": [], "category_specific_documents": []}


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest):
    question = payload.question.strip()
    if len(question) < 3:
        raise HTTPException(status_code=422, detail="Please enter a more specific question.")

    async def event_generator():
        yield f"data: {json.dumps({'type': 'step', 'message': 'Parsing student profile and admission intent...'})}\n\n"
        await asyncio.sleep(0.05)

        # Sync profile if provided
        try:
            from interactive_terminal import get_engine
            engine = get_engine()
            if payload.profile and engine.orch:
                engine.orch._conv_context.update({
                    "percentile": payload.profile.get("percentile"),
                    "rank": payload.profile.get("merit_rank"),
                    "category": payload.profile.get("category"),
                    "location": payload.profile.get("preferred_location"),
                    "preferred_branches": payload.profile.get("preferred_branches"),
                })
        except Exception:
            pass

        yield f"data: {json.dumps({'type': 'step', 'message': 'Querying official CET Cell cutoff database across CAP rounds...'})}\n\n"
        await asyncio.sleep(0.08)

        # Process query
        try:
            from interactive_terminal import get_engine
            engine = get_engine()
            result = engine.answer_query(question, use_llm=payload.use_llm)

            # If shortlist is available, emit instant structured table event
            if isinstance(result, dict) and result.get("shortlist"):
                yield f"data: {json.dumps({'type': 'shortlist', 'shortlist': result['shortlist'][:30], 'count': len(result['shortlist'])})}\n\n"

            # Progressively stream the answer tokens
            answer_text = result.get("message") or result.get("answer") or "Here is the verified cutoff evidence from the Maharashtra CET Cell records."
            words = answer_text.split(" ")
            chunk_size = 4
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i + chunk_size]) + " "
                yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
                await asyncio.sleep(0.02)

            yield f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/whatsapp/webhook")
def whatsapp_verify(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
) -> Response:
    verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "aicon_secret_token_2026")
    if hub_mode == "subscribe" and hub_token == verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(content="Verification failed", status_code=403)


@app.post("/api/whatsapp/webhook")
def whatsapp_message(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        from interactive_terminal import get_engine
        engine = get_engine()

        incoming_text = "Pune colleges for Computer Engineering with 94 percentile"
        try:
            entry = payload.get("entry", [])[0]
            change = entry.get("changes", [])[0].get("value", {})
            message_obj = change.get("messages", [])[0]
            incoming_text = message_obj.get("text", {}).get("body", incoming_text)
        except Exception:
            if "message" in payload:
                incoming_text = str(payload["message"])

        res = engine.answer_query(incoming_text)
        ans = res.get("message") or res.get("answer") or "No matching cutoff records found."
        wa_text = "🎓 *AI-CON Admission Intelligence*\n\n" + ans[:1400]
        return {"status": "success", "reply": wa_text}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    question = payload.question.strip()
    if len(question) < 3:
        raise HTTPException(status_code=422, detail="Please enter a more specific question.")

    try:
        from interactive_terminal import get_engine
        engine = get_engine()

        # Sync profile if provided
        if payload.profile and engine.orch:
            engine.orch._conv_context.update({
                "percentile": payload.profile.get("percentile"),
                "rank": payload.profile.get("merit_rank"),
                "category": payload.profile.get("category"),
                "location": payload.profile.get("preferred_location"),
                "preferred_branches": payload.profile.get("preferred_branches"),
            })

        result = engine.answer_query(question, use_llm=payload.use_llm)

        # Optional grounded LLM generation if user requested use_llm
        if payload.use_llm and isinstance(result, dict) and not result.get("llm_generated"):
            evidence = str(result.get("evidence", "") or "")
            pipeline_status = str(result.get("status", ""))
            blocked = {"needs_clarification", "unavailable", "pipeline_error", "error"}
            if pipeline_status not in blocked and evidence.strip():
                try:
                    grounded_ans = generate_grounded_answer(question, evidence, root=ROOT)
                    if grounded_ans:
                        result["answer"] = grounded_ans
                        result["model"] = "TinyLlama 1.1B Chat + AI-CON LoRA adapter"
                        result["inference_backend"] = "Transformers + PEFT"
                except Exception as exc:
                    result["llm_skipped_reason"] = f"Local LLM generation skipped: {exc}"

        return {"status": "ok", "question": question, "result": result}
    except Exception as exc:
        return {
            "status": "pipeline_error",
            "question": question,
            "return_code": 1,
            "message": f"Query processing exception: {exc}",
            "stderr": str(exc),
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("aicon_ui.app:app", host="127.0.0.1", port=8000, reload=False)
