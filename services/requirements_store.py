from __future__ import annotations

import json
import sqlite3
from datetime import datetime, UTC

from models.db import DB_PATH, init_db
from services.parser import parse_requirements


def save_requirements_snapshot(
    raw_text: str,
    source_key: str | None = None,
    source_type: str | None = None,
    source_label: str | None = None,
    mode: str | None = None,
) -> dict:
    init_db()
    categorized = parse_requirements(raw_text=raw_text)
    items: list[dict] = []
    for requirement_type in ["FIT", "PARTIAL", "GAP"]:
        items.extend(categorized.get(requirement_type, []))

    if not items:
        raise ValueError("No valid requirements were parsed from the provided input.")

    timestamp = datetime.now(UTC).isoformat()
    normalized_json = json.dumps(items, indent=2)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO saved_requirements (
                source_key, source_type, source_label, mode, raw_text, normalized_json, item_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                source_type=excluded.source_type,
                source_label=excluded.source_label,
                mode=excluded.mode,
                raw_text=excluded.raw_text,
                normalized_json=excluded.normalized_json,
                item_count=excluded.item_count,
                updated_at=excluded.updated_at
            """,
            (
                source_key or "__global__",
                source_type or "unknown",
                source_label or "",
                mode or "json",
                raw_text,
                normalized_json,
                len(items),
                timestamp,
                timestamp,
            ),
        )

        row = conn.execute(
            "SELECT id, source_key, mode, item_count, updated_at FROM saved_requirements WHERE source_key=?",
            (source_key or "__global__",),
        ).fetchone()

    return {
        "id": row["id"] if row else cursor.lastrowid,
        "source_key": row["source_key"] if row else (source_key or "__global__"),
        "mode": row["mode"] if row else (mode or "json"),
        "item_count": row["item_count"] if row else len(items),
        "updated_at": row["updated_at"] if row else timestamp,
    }


def get_requirements_snapshot(source_key: str | None = None) -> dict | None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, source_key, source_type, source_label, mode, raw_text, normalized_json, item_count, created_at, updated_at
            FROM saved_requirements
            WHERE source_key=?
            """,
            (source_key or "__global__",),
        ).fetchone()

    if not row:
        return None

    return {
        "id": row["id"],
        "source_key": row["source_key"],
        "source_type": row["source_type"],
        "source_label": row["source_label"],
        "mode": row["mode"],
        "raw_text": row["raw_text"] or "",
        "normalized_json": row["normalized_json"] or "[]",
        "item_count": row["item_count"] or 0,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
