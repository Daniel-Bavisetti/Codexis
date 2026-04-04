from __future__ import annotations

import json


def _normalize_display_path(value: str) -> str:
    normalized = str(value or "").replace("\\", "/")
    if not normalized:
        return "Unknown"

    if "data/codebase/" in normalized:
        return normalized.split("data/codebase/", 1)[1]

    parts = [part for part in normalized.split("/") if part]

    temp_index = next(
        (index for index, part in enumerate(parts) if part.startswith("req-to-code-upload-") or part.startswith("req-to-code-")),
        -1,
    )
    if temp_index >= 0 and temp_index + 1 < len(parts):
        return "/".join(parts[temp_index + 1:])

    persistent_index = next((index for index, part in enumerate(parts) if part == "github-repos"), -1)
    if persistent_index >= 0 and persistent_index + 1 < len(parts):
        return "/".join(parts[persistent_index + 1:])

    return normalized


def _parse_json(value, default):
    if not value:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def present_change(change: dict, attempts: list[dict], feedback: list[dict], impact: dict | None) -> dict:
    latest_review = _parse_json(change.get("review_comment"), {})
    latest_impact = impact or {
        "impacted_files": [],
        "impacted_functions": [],
        "dependency_chain": [],
        "risk_score": 0.0,
        "summary": "",
    }

    presented_attempts = []
    for attempt in attempts:
        presented_attempts.append(
            {
                **attempt,
                "review": _parse_json(attempt.get("review_json"), {}),
                "context": _parse_json(attempt.get("context_json"), []),
                "impact_analysis": _parse_json(attempt.get("impact_json"), {}),
            }
        )

    return {
        **change,
        "file_path": _normalize_display_path(change.get("file_path", "")),
        "review": latest_review,
        "impact_analysis": latest_impact,
        "attempt_history": presented_attempts,
        "feedback_history": feedback,
    }
