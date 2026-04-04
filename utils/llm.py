import json
import os
import socket
from pathlib import Path
from urllib import error, request


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_TIMEOUT_SECONDS = 180
_DOTENV_CACHE: dict[str, str] | None = None


def _load_dotenv() -> dict[str, str]:
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return _DOTENV_CACHE

    env_path = Path(__file__).resolve().parents[1] / ".env"
    values: dict[str, str] = {}
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

    _DOTENV_CACHE = values
    return values


def _config_value(name: str, default: str | None = None) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    dotenv_values = _load_dotenv()
    if dotenv_values.get(name):
        return dotenv_values[name]
    return default


def _runtime_config() -> tuple[str | None, bool]:
    api_key = _config_value("GEMINI_API_KEY")
    allow_mock = (_config_value("ALLOW_MOCK_LLM", "false") or "false").lower() == "true"
    return api_key, allow_mock


def llm_status() -> dict:
    api_key, allow_mock = _runtime_config()
    return {
        "api_key_present": bool(api_key),
        "sdk_available": True,
        "mock_enabled": allow_mock,
        "ready": bool(api_key),
    }


def call_llm(prompt: str) -> str:
    """Reusable Gemini REST wrapper with runtime configuration lookup."""
    api_key, allow_mock = _runtime_config()
    gemini_model = _config_value("GEMINI_MODEL", DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL
    gemini_api_base = _config_value("GEMINI_API_BASE", DEFAULT_GEMINI_API_BASE) or DEFAULT_GEMINI_API_BASE
    timeout_seconds = int(_config_value("GEMINI_TIMEOUT_SECONDS", str(DEFAULT_GEMINI_TIMEOUT_SECONDS)) or DEFAULT_GEMINI_TIMEOUT_SECONDS)

    if not api_key:
        if allow_mock:
            if '"confidence"' in prompt or "dependency_violations" in prompt:
                return '{"issues": [], "suggestions": ["Mock reviewer used because ALLOW_MOCK_LLM=true."], "dependency_violations": [], "security_findings": [], "confidence": 0.72, "verdict": "PASS"}'
            return "# MOCK GENERATION\ndef mock_func():\n    pass"
        return "Error: LLM unavailable (GEMINI_API_KEY is not set). Set GEMINI_API_KEY, or set ALLOW_MOCK_LLM=true."

    try:
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ]
                }
            ]
        }
        req = request.Request(
            url=f"{gemini_api_base}/{gemini_model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )

        with request.urlopen(req, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))

        candidates = data.get("candidates", [])
        if not candidates:
            return "Error: Gemini API returned no candidates."

        parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        return text.strip() if text else "Error: Gemini API returned an empty response."
    except error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            detail = str(exc)
        return f"Error: Gemini API HTTP {exc.code}: {detail}"
    except error.URLError as exc:
        return f"Error: Gemini API network error: {exc.reason}"
    except TimeoutError:
        return f"Error: Gemini API request timed out after {timeout_seconds} seconds."
    except socket.timeout:
        return f"Error: Gemini API request timed out after {timeout_seconds} seconds."
    except Exception as exc:
        return f"Error: {exc}"
