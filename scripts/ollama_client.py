"""
Local Ollama Client for AI-con (Phase 2)
----------------------------------------
Connects to the local Ollama daemon (default: http://localhost:11434) running
the local model (default: qwen2.5:7b).

Strictly offline & local:
- Uses the standard library (urllib.request / json) with zero external network calls.
- Never downloads models or redirects to paid APIs.
- Operates at temperature 0.0 for deterministic, grounded evidence extraction.
- Maps connection errors, timeouts, and missing model errors into typed exceptions.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class OllamaError(RuntimeError):
    """Base exception for Ollama communication failures."""
    pass


class OllamaConnectionError(OllamaError):
    """Raised when the Ollama daemon cannot be reached."""
    pass


class OllamaModelError(OllamaError):
    """Raised when the requested model is not found on the Ollama daemon."""
    pass


def call_ollama(
    system: str,
    user: str,
    model: str = "qwen2.5:7b",
    host: str = "http://localhost:11434",
    timeout: float = 60.0,
    temperature: float = 0.0,
) -> str:
    """Send system and user prompts to local Ollama /api/chat and return text.

    Args:
        system: Anti-hallucination system prompt instructing the model to answer
                strictly from evidence.
        user: Formatted prompt containing retrieved evidence chunks and student question.
        model: Installed local Ollama model tag (default: qwen2.5:7b).
        host: Local Ollama daemon URL (default: http://localhost:11434).
        timeout: Socket timeout in seconds (default: 60.0).
        temperature: Sampling temperature (default: 0.0 for deterministic factual answers).

    Returns:
        The generated assistant response string.

    Raises:
        OllamaConnectionError: If Ollama daemon is not running or unreachable.
        OllamaModelError: If model is missing from local Ollama library.
        OllamaError: For invalid response payloads or other API issues.
    """
    clean_host = host.rstrip("/")
    url = f"{clean_host}/api/chat"

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
            data = json.loads(raw_body)
    except urllib.error.HTTPError as exc:
        err_msg = str(exc)
        try:
            err_body = exc.read().decode("utf-8")
            err_json = json.loads(err_body)
            err_msg = err_json.get("error", err_body)
        except Exception:
            pass

        if exc.code == 404:
            raise OllamaModelError(
                f"Ollama model '{model}' not found on {clean_host} (HTTP 404: {err_msg}). "
                f"Verify the model exists locally using 'ollama list'."
            ) from exc
        raise OllamaError(f"Ollama API returned HTTP {exc.code}: {err_msg}") from exc
    except urllib.error.URLError as exc:
        raise OllamaConnectionError(
            f"Failed to connect to local Ollama daemon at {clean_host} ({exc.reason}). "
            f"Ensure Ollama is running ('ollama serve' or start the Ollama desktop app)."
        ) from exc
    except TimeoutError as exc:
        raise OllamaConnectionError(
            f"Ollama request to {clean_host} timed out after {timeout} seconds."
        ) from exc
    except json.JSONDecodeError as exc:
        raise OllamaError(f"Invalid JSON response received from Ollama: {exc}") from exc
    except Exception as exc:
        raise OllamaError(f"Unexpected error communicating with Ollama: {exc}") from exc

    msg = data.get("message")
    if not isinstance(msg, dict) or "content" not in msg:
        raise OllamaError(f"Ollama response missing 'message.content': {data}")

    return str(msg.get("content", "")).strip()
