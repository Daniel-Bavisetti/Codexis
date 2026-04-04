from __future__ import annotations

import sqlite3

from models.db import DB_PATH, init_db
from utils.llm import call_llm, llm_status


class FileSummaryService:
    def __init__(self) -> None:
        init_db()

    def get_or_create_summaries(self, codebase: dict[str, str], parsed_files: dict[str, object]) -> dict[str, str]:
        summaries: dict[str, str] = {}
        runtime = llm_status()
        for path, content in codebase.items():
            existing = self._get_summary(path)
            if existing:
                summaries[path] = existing
                continue

            language = getattr(parsed_files.get(path), "language", "unknown")
            summary = self._generate_summary(path, language, content, runtime)
            self._store_summary(path, language, summary)
            summaries[path] = summary
        return summaries

    def _get_summary(self, file_path: str) -> str | None:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT summary FROM file_summaries WHERE file_path=?",
                (file_path,),
            ).fetchone()
            return row[0] if row and row[0] else None

    def _store_summary(self, file_path: str, language: str, summary: str) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO file_summaries (file_path, language, summary)
                VALUES (?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    language=excluded.language,
                    summary=excluded.summary
                """,
                (file_path, language, summary),
            )

    def _generate_summary(self, file_path: str, language: str, content: str, runtime: dict) -> str:
        if not runtime["ready"] and not runtime["mock_enabled"]:
            return f"LLM summary unavailable for {file_path} because the LLM runtime is not configured."

        prompt = f"""Summarize this source file as a module summary for a developer dashboard.
Write 2-4 clear sentences.
Sentence 1 should state the module's main responsibility.
Sentence 2 should mention the key classes, functions, or APIs it exposes.
Sentence 3 should mention any important behavior, side effects, or integration points if they exist.
Keep the summary concrete and readable.
Do not include markdown, bullet points, or headings.

File: {file_path}
Language: {language}

Code:
{content}
"""
        result = call_llm(prompt).strip()
        if result.startswith("Error:"):
            return f"LLM summary unavailable for {file_path}: {result}"
        return result
