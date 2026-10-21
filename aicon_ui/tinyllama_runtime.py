"""Lazy runtime for AI-CON's trained TinyLlama + LoRA adapter.

This module intentionally imports torch/transformers/peft only when inference is
requested, so the UI can start in evidence-only mode without ML dependencies.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

_MODEL: Any = None
_TOKENIZER: Any = None
_DEVICE: Any = None
_LOAD_LOCK = threading.Lock()
_GENERATE_LOCK = threading.Lock()
_MODEL_NAME: str | None = None


def _root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root).expanduser().resolve()
    configured = os.environ.get("AI_CON_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def _paths(root: str | Path | None = None) -> tuple[Path, Path, dict[str, Any] | None]:
    project_root = _root(root)
    adapter_dir = Path(
        os.environ.get("AI_CON_MODEL_ADAPTER_DIR", str(project_root / "model_artifacts" / "lora_adapter"))
    ).expanduser().resolve()
    config_path = adapter_dir / "adapter_config.json"
    config: dict[str, Any] | None = None
    if config_path.is_file():
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                config = loaded
        except (OSError, json.JSONDecodeError):
            config = None
    return project_root, adapter_dir, config


def _base_model_cached(base_model: str | None) -> bool:
    if not base_model:
        return False
    local_path = Path(base_model).expanduser()
    if local_path.exists():
        return True
    if "/" not in base_model:
        return False
    cache_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")).expanduser()
    hub_dir = cache_home / "hub"
    # Hugging Face's standard repository folder naming convention.
    repo_dir = hub_dir / ("models--" + base_model.replace("/", "--"))
    snapshots = repo_dir / "snapshots"
    try:
        return snapshots.is_dir() and any(
            (snapshot / "config.json").is_file()
            and any(snapshot.glob("*.safetensors"))
            for snapshot in snapshots.iterdir()
            if snapshot.is_dir()
        )
    except OSError:
        return False


def model_status(root: str | Path | None = None) -> dict[str, Any]:
    """Return model readiness without downloading or loading weights."""
    _, adapter_dir, config = _paths(root)
    adapter_weights = (adapter_dir / "adapter_model.safetensors").is_file() or (
        adapter_dir / "adapter_model.bin"
    ).is_file()
    base_model = os.environ.get("AI_CON_BASE_MODEL") or (
        str(config.get("base_model_name_or_path")) if config else None
    )
    deps = {}
    try:
        from importlib.util import find_spec
        for module in ("torch", "transformers", "peft", "accelerate", "safetensors"):
            deps[module] = find_spec(module) is not None
    except (ImportError, ValueError):
        deps = {module: False for module in ("torch", "transformers", "peft", "accelerate", "safetensors")}
    dependencies_ready = bool(deps) and all(deps.values())
    adapter_found = bool(config and adapter_weights and base_model)
    available = adapter_found and dependencies_ready
    base_cached = _base_model_cached(base_model)
    if not adapter_found:
        message = f"Trained adapter/config not found or invalid: {adapter_dir}"
    elif not dependencies_ready:
        missing = [name for name, found in deps.items() if not found]
        message = "Install the trained-model dependencies; missing: " + ", ".join(missing)
    elif base_cached:
        message = "TinyLlama base model and AI-CON LoRA adapter are detected. Weights load on first use."
    else:
        message = "Adapter is detected. The TinyLlama base weights are not cached and will download from Hugging Face on first use."
    return {
        "available": available,
        "loaded": _MODEL is not None,
        "adapter_found": adapter_found,
        "adapter_path": str(adapter_dir),
        "base_model": base_model,
        "base_model_cached": base_cached,
        "dependencies_ready": dependencies_ready,
        "dependencies": deps,
        "message": message,
        "backend": "Transformers + PEFT",
    }


def _load(root: str | Path | None = None) -> tuple[Any, Any, Any, str]:
    global _MODEL, _TOKENIZER, _DEVICE, _MODEL_NAME
    if _MODEL is not None and _TOKENIZER is not None:
        return _MODEL, _TOKENIZER, _DEVICE, _MODEL_NAME or "TinyLlama + LoRA"

    with _LOAD_LOCK:
        if _MODEL is not None and _TOKENIZER is not None:
            return _MODEL, _TOKENIZER, _DEVICE, _MODEL_NAME or "TinyLlama + LoRA"

        _, adapter_dir, config = _paths(root)
        if not config or not (
            (adapter_dir / "adapter_model.safetensors").is_file()
            or (adapter_dir / "adapter_model.bin").is_file()
        ):
            raise FileNotFoundError(
                f"AI-CON LoRA adapter files were not found in {adapter_dir}."
            )

        configured_base = str(config.get("base_model_name_or_path") or "").strip()
        base_model = os.environ.get("AI_CON_BASE_MODEL", configured_base).strip()
        if not base_model:
            raise ValueError("adapter_config.json does not specify base_model_name_or_path.")
        if configured_base and os.environ.get("AI_CON_BASE_MODEL") and base_model != configured_base:
            raise ValueError(
                "AI_CON_BASE_MODEL does not match the base model declared by the adapter. "
                f"Expected {configured_base!r}, received {base_model!r}."
            )

        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "TinyLlama inference dependencies are missing. Activate the UI environment and run "
                "python -m pip install -r aicon_ui/requirements-model.txt."
            ) from exc

        if hasattr(torch, "set_num_threads"):
            torch.set_num_threads(max(1, min(os.cpu_count() or 2, 4)))
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float16 if device.type == "cuda" else torch.float32

        tokenizer = AutoTokenizer.from_pretrained(base_model)
        if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
            tokenizer.pad_token = tokenizer.eos_token

        base = AutoModelForCausalLM.from_pretrained(
            base_model,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
        )
        model = PeftModel.from_pretrained(base, str(adapter_dir), is_trainable=False)
        model.to(device)
        model.eval()

        _MODEL = model
        _TOKENIZER = tokenizer
        _DEVICE = device
        _MODEL_NAME = f"{base_model} + AI-CON LoRA adapter"
        return _MODEL, _TOKENIZER, _DEVICE, _MODEL_NAME


def generate_text(system: str, user: str, root: str | Path | None = None, max_new_tokens: int = 256) -> str:
    """Generate one deterministic response using the saved LoRA adapter."""
    model, tokenizer, device, _ = _load(root)
    try:
        if getattr(tokenizer, "chat_template", None):
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            # Fallback for a compatible TinyLlama tokenizer with no registered template.
            prompt = (
                f"<|system|>\n{system}</s>\n"
                f"<|user|>\n{user}</s>\n"
                "<|assistant|>\n"
            )
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=1700,
        )
        inputs = {key: value.to(device) for key, value in inputs.items()}
        input_length = int(inputs["input_ids"].shape[-1])
        with _GENERATE_LOCK:
            import torch
            with torch.inference_mode():
                output = model.generate(
                    **inputs,
                    max_new_tokens=max(32, min(int(max_new_tokens), 320)),
                    do_sample=False,
                    repetition_penalty=1.05,
                    pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                    use_cache=True,
                )
        answer = tokenizer.decode(output[0][input_length:], skip_special_tokens=True).strip()
        if not answer:
            raise RuntimeError("The trained model returned an empty answer.")
        return answer
    except Exception:
        # Keep the loaded model cached. The caller will report the actual error.
        raise


def generate_grounded_answer(question: str, evidence: str, root: str | Path | None = None) -> str:
    """Generate a response constrained to the retrieved evidence."""
    system = (
        "You are AI-CON Guide, an admission decision-support assistant for Maharashtra engineering admissions.\n"
        "Rules:\n"
        "1. Answer only from the supplied EVIDENCE. Do not use memory or outside assumptions as factual evidence.\n"
        "2. If the evidence does not contain the requested fact, state that it is unavailable in the retrieved records.\n"
        "3. Never invent college information, affiliation, fees, placements, cutoff, rank, percentile, seat counts, or dates.\n"
        "4. Never guarantee admission. Historical cutoffs are not promises of future allotment.\n"
        "5. Copy each evidence citation tag exactly as shown. Do not invent citations or modify their identifiers.\n"
        "6. Give a concise, readable answer and explicitly mention uncertainty or missing fields."
    )
    user = (
        f"EVIDENCE:\n{evidence}\n\nQUESTION: {question}\n\n"
        "Answer from this evidence only. Preserve exact source identifiers in square brackets when citing them."
    )
    answer = generate_text(system, user, root=root)
    # Remove citation-looking tokens that do not occur in the supplied evidence.
    import re
    valid = set(re.findall(r"\[([A-Za-z0-9_:\-]+)\]", evidence or ""))
    def keep_only_valid(match: re.Match[str]) -> str:
        token = match.group(1)
        return match.group(0) if token in valid else ""
    answer = re.sub(r"\[([A-Za-z0-9_:\-]+)\]", keep_only_valid, answer)
    answer = re.sub(r"[ \t]{2,}", " ", answer).strip()
    return answer


def is_loaded() -> bool:
    return _MODEL is not None and _TOKENIZER is not None
