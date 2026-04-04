from __future__ import annotations

import json
import os
from datetime import datetime, UTC


class LearningEngine:
    def __init__(self, path: str = "data/memory.json") -> None:
        self.path = path

    def _default_memory(self) -> dict:
        return {
            "successful_patterns": [],
            "rejected_attempts": [],
            "reviewer_feedback": [],
            "attempt_log": [],
            "common_issues": [],
        }

    def _normalize_memory(self, memory: dict | None) -> dict:
        normalized = self._default_memory()
        if isinstance(memory, dict):
            normalized.update(memory)
        for key in ("successful_patterns", "rejected_attempts", "reviewer_feedback", "attempt_log", "common_issues"):
            if not isinstance(normalized.get(key), list):
                normalized[key] = []
        return normalized

    def load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    return self._normalize_memory(json.load(handle))
            except (OSError, json.JSONDecodeError):
                pass
        return self._default_memory()

    def save(self, memory: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(memory, handle, indent=2)

    def record_attempt(self, requirement_id: str, file_path: str, attempt_number: int, confidence: float, outcome: str) -> None:
        memory = self.load()
        memory["attempt_log"].append(
            {
                "requirement_id": requirement_id,
                "file_path": file_path,
                "attempt_number": attempt_number,
                "confidence": confidence,
                "outcome": outcome,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        self.save(memory)

    def record_success(self, requirement_id: str, file_path: str, review: dict) -> None:
        memory = self.load()
        memory["successful_patterns"].append(
            {
                "requirement_id": requirement_id,
                "file_path": file_path,
                "review": review,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        self.save(memory)

    def record_rejection(self, requirement_id: str, file_path: str, feedback: str, attempt_number: int) -> None:
        memory = self.load()
        memory["rejected_attempts"].append(
            {
                "requirement_id": requirement_id,
                "file_path": file_path,
                "feedback": feedback,
                "attempt_number": attempt_number,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        memory["reviewer_feedback"].append(
            {
                "requirement_id": requirement_id,
                "file_path": file_path,
                "feedback": feedback,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        self.save(memory)

    def get_context(self, requirement_id: str, limit: int = 5) -> dict:
        memory = self.load()

        return {
            "successful_patterns": [
                item for item in memory.get("successful_patterns", [])
                if item.get("requirement_id") == requirement_id
            ][-limit:],

            "rejected_attempts": [
                item for item in memory.get("rejected_attempts", [])
                if item.get("requirement_id") == requirement_id
            ][-limit:],

            "reviewer_feedback": [
                item for item in memory.get("reviewer_feedback", [])
                if item.get("requirement_id") == requirement_id
            ][-limit:]
        }
