from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, UTC
from pathlib import Path

from models.db import DB_PATH
from services.learning_engine import LearningEngine
from ui.change_presenter import present_change


PROTECTED_FILES = ["main.py", "api/routes.py", "models/db.py", "services/pipeline.py"]
RISK_THRESHOLD = float(os.environ.get("IMPACT_RISK_THRESHOLD", "0.85"))
RUNTIME_STATE_PATH = Path("data/runtime_state.json")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def read_runtime_state() -> dict:
    if not RUNTIME_STATE_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_runtime_state(state: dict) -> None:
    RUNTIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _clear_generated_artifacts(codebase_path: str | None) -> list[str]:
    removed: list[str] = []
    if not codebase_path:
        return removed

    root = Path(codebase_path)
    artifact_dir = root / ".req-to-code"
    backup_dir = root / ".backups"

    for target in [artifact_dir, backup_dir]:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            removed.append(str(target))

    if "req-to-code-upload-" in str(root):
        for candidate in [root, root.parent]:
            name = candidate.name
            if name.startswith("req-to-code-upload-") and candidate.exists():
                shutil.rmtree(candidate, ignore_errors=True)
                removed.append(str(candidate))
                break

    return removed


def clear_codebase_dependent_state(codebase_path: str | None = None) -> dict:
    print(f"[codebase-reset] clearing database state for previous codebase={codebase_path or '<none>'}")
    with _connect() as conn:
        conn.execute("DELETE FROM feedback")
        conn.execute("DELETE FROM impact_analysis")
        conn.execute("DELETE FROM attempts")
        conn.execute("DELETE FROM changes")
        conn.execute("DELETE FROM graph_snapshots")
        conn.execute("DELETE FROM file_summaries")
        conn.execute("DELETE FROM audit_log")
        conn.execute("DELETE FROM sqlite_sequence")

    removed_paths = _clear_generated_artifacts(codebase_path)
    write_runtime_state({})
    if removed_paths:
        print(f"[codebase-reset] removed generated paths: {', '.join(removed_paths)}")
    else:
        print("[codebase-reset] no generated paths needed removal")
    return {
        "cleared_db": True,
        "removed_paths": removed_paths,
    }


def sync_codebase_runtime_state(source_key: str | None, codebase_path: str | None, source_meta: dict | None = None) -> dict:
    current = read_runtime_state()
    previous_key = current.get("source_key")
    previous_path = current.get("codebase_path")
    changed = bool(source_key) and previous_key not in (None, source_key)

    reset_result = None
    if changed:
        print(f"[codebase-reset] source changed from {previous_key} to {source_key}")
        reset_result = clear_codebase_dependent_state(previous_path)

    next_state = {
        "source_key": source_key,
        "codebase_path": codebase_path,
    }
    if source_meta:
        next_state.update(source_meta)
    write_runtime_state(next_state)
    return {
        "changed": changed,
        "previous_source_key": previous_key,
        "reset_result": reset_result,
    }


def log_event(event_type: str, payload: dict, change_id: int | None = None, attempt_id: int | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (event_type, change_id, attempt_id, payload) VALUES (?, ?, ?, ?)",
            (event_type, change_id, attempt_id, json.dumps(payload)),
        )


def get_change_by_requirement(requirement_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM changes WHERE requirement_id=? ORDER BY id DESC LIMIT 1",
            (requirement_id,),
        ).fetchone()
        return dict(row) if row else None


def get_change(change_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM changes WHERE id=?", (change_id,)).fetchone()
        return dict(row) if row else None


def ensure_change(requirement_id: str, file_path: str, original_code: str) -> int:
    existing = get_change_by_requirement(requirement_id)
    timestamp = datetime.now(UTC).isoformat()
    if existing:
        with _connect() as conn:
            conn.execute(
                """
                UPDATE changes
                SET file_path=?, original_code=?, updated_at=?
                WHERE id=?
                """,
                (file_path, original_code, timestamp, existing["id"]),
            )
        return existing["id"]

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO changes (
                requirement_id, file_path, original_code, generated_code, diff, review_comment,
                status, confidence, confidence_explanation, rejection_history, feedback_comments,
                latest_attempt, attempts_count, impact_summary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                requirement_id,
                file_path,
                original_code,
                "",
                "",
                "{}",
                "PENDING",
                0.0,
                "",
                "",
                "",
                None,
                0,
                "",
                timestamp,
                timestamp,
            ),
        )
        return cursor.lastrowid


def get_attempt_count(change_id: int) -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM attempts WHERE change_id=?", (change_id,)).fetchone()
        return int(row["total"]) if row else 0


def get_latest_attempt(change_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM attempts WHERE change_id=? ORDER BY attempt_number DESC LIMIT 1",
            (change_id,),
        ).fetchone()
        return dict(row) if row else None


def record_attempt(
    change_id: int,
    attempt_number: int,
    generated_code: str,
    diff_text: str,
    review: dict,
    validation_message: str,
    confidence: float,
    confidence_explanation: str,
    context: list[dict],
    feedback_used: str,
    impact_analysis: dict,
    status: str = "PENDING",
) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO attempts (
                change_id, attempt_number, generated_code, diff, review_json, validation_message,
                status, confidence, confidence_explanation, context_json, feedback_used, impact_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                change_id,
                attempt_number,
                generated_code,
                diff_text,
                json.dumps(review),
                validation_message,
                status,
                confidence,
                confidence_explanation,
                json.dumps(context),
                feedback_used,
                json.dumps(impact_analysis),
            ),
        )
        attempt_id = cursor.lastrowid
        conn.execute(
            """
            UPDATE changes
            SET generated_code=?, diff=?, review_comment=?, status=?, confidence=?, confidence_explanation=?,
                latest_attempt=?, attempts_count=?, impact_summary=?, updated_at=?
            WHERE id=?
            """,
            (
                generated_code,
                diff_text,
                json.dumps(review),
                status,
                confidence,
                confidence_explanation,
                attempt_id,
                attempt_number,
                impact_analysis.get("summary", ""),
                datetime.now(UTC).isoformat(),
                change_id,
            ),
        )
    log_event(
        "ATTEMPT_RECORDED",
        {"attempt_number": attempt_number, "status": status, "confidence": confidence},
        change_id=change_id,
        attempt_id=attempt_id,
    )
    return attempt_id


def record_impact_analysis(change_id: int, attempt_id: int, impact_analysis: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO impact_analysis (
                change_id, attempt_id, impacted_files, impacted_functions, dependency_chain, risk_score, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                change_id,
                attempt_id,
                json.dumps(impact_analysis.get("impacted_files", [])),
                json.dumps(impact_analysis.get("impacted_functions", [])),
                json.dumps(impact_analysis.get("dependency_chain", [])),
                impact_analysis.get("risk_score", 0.0),
                impact_analysis.get("summary", ""),
            ),
        )
    log_event("IMPACT_ANALYZED", impact_analysis, change_id=change_id, attempt_id=attempt_id)


def record_feedback(change_id: int, attempt_id: int | None, decision: str, comment: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO feedback (change_id, attempt_id, decision, comment) VALUES (?, ?, ?, ?)",
            (change_id, attempt_id, decision, comment),
        )
    log_event("HITL_FEEDBACK", {"decision": decision, "comment": comment}, change_id=change_id, attempt_id=attempt_id)


def update_status(change_id: int, status: str, comment: str | None = None) -> None:
    latest_attempt = get_latest_attempt(change_id)
    change = get_change(change_id) or {}
    with _connect() as conn:
        if comment and status == "REJECTED":
            row = conn.execute("SELECT rejection_history, feedback_comments FROM changes WHERE id=?", (change_id,)).fetchone()
            rejection_history = (row["rejection_history"] or "") + f"[{status}] {comment}\n"
            feedback_comments = (row["feedback_comments"] or "") + f"{comment}\n"
            conn.execute(
                """
                UPDATE changes
                SET status=?, rejection_history=?, feedback_comments=?, updated_at=?
                WHERE id=?
                """,
                (status, rejection_history, feedback_comments.strip(), datetime.now(UTC).isoformat(), change_id),
            )
        else:
            conn.execute(
                "UPDATE changes SET status=?, updated_at=? WHERE id=?",
                (status, datetime.now(UTC).isoformat(), change_id),
            )
        if latest_attempt:
            conn.execute("UPDATE attempts SET status=? WHERE id=?", (status, latest_attempt["id"]))

    if comment:
        record_feedback(change_id, latest_attempt["id"] if latest_attempt else None, status, comment)
        if status == "REJECTED" and change:
            LearningEngine().record_rejection(
                change.get("requirement_id", "UNKNOWN"),
                change.get("file_path", "N/A"),
                comment,
                latest_attempt["attempt_number"] if latest_attempt else 0,
            )
    log_event("STATUS_UPDATED", {"status": status, "comment": comment}, change_id=change_id, attempt_id=latest_attempt["id"] if latest_attempt else None)


def get_latest_feedback(change_id: int) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT comment FROM feedback WHERE change_id=? ORDER BY id DESC LIMIT 1",
            (change_id,),
        ).fetchone()
        return row["comment"] if row else None


def get_latest_impact(change_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT impacted_files, impacted_functions, dependency_chain, risk_score, summary
            FROM impact_analysis
            WHERE change_id=?
            ORDER BY id DESC LIMIT 1
            """,
            (change_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "impacted_files": json.loads(row["impacted_files"] or "[]"),
            "impacted_functions": json.loads(row["impacted_functions"] or "[]"),
            "dependency_chain": json.loads(row["dependency_chain"] or "[]"),
            "risk_score": row["risk_score"] or 0.0,
            "summary": row["summary"] or "",
        }


def save_graph_snapshot(scope_path: str, graph: dict) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO graph_snapshots (scope_path, graph_json) VALUES (?, ?)",
            (scope_path, json.dumps(graph)),
        )
        snapshot_id = cursor.lastrowid
    log_event("GRAPH_SNAPSHOT_SAVED", {"scope_path": scope_path, "snapshot_id": snapshot_id})
    return snapshot_id


def get_changes() -> list[dict]:
    with _connect() as conn:
        change_rows = conn.execute("SELECT * FROM changes ORDER BY updated_at DESC, id DESC").fetchall()
        results: list[dict] = []
        for change_row in change_rows:
            change = dict(change_row)
            attempts = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM attempts WHERE change_id=? ORDER BY attempt_number DESC",
                    (change["id"],),
                ).fetchall()
            ]
            feedback = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM feedback WHERE change_id=? ORDER BY id DESC",
                    (change["id"],),
                ).fetchall()
            ]
            results.append(present_change(change, attempts, feedback, get_latest_impact(change["id"])))
        return results


def rollback_change(backup_path: str, target_path: str) -> tuple[bool, str]:
    try:
        shutil.copyfile(backup_path, target_path)
        return True, f"Rolled back {target_path} from {backup_path}"
    except OSError as exc:
        return False, f"Rollback failed: {exc}"


def apply_diff(change_id: int, base_dir: str = "data/codebase") -> tuple[bool, str]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM changes WHERE id=?", (change_id,)).fetchone()
    if not row:
        return False, "Change not found"

    latest_impact = get_latest_impact(change_id) or {"risk_score": 0.0}
    if latest_impact.get("risk_score", 0.0) > RISK_THRESHOLD:
        return False, f"Impact Analyzer blocked apply. Risk score {latest_impact['risk_score']} exceeded threshold {RISK_THRESHOLD}."

    file_path = row["file_path"]
    if any(protected == file_path or file_path.endswith(protected) for protected in PROTECTED_FILES):
        return False, f"Safety Layer: Modification of protected file {file_path} is blocked."

    if os.path.isabs(file_path) or file_path.startswith(base_dir):
        target_path = file_path
    else:
        target_path = os.path.join(base_dir, file_path)
    target_dir = os.path.dirname(target_path)
    os.makedirs(target_dir, exist_ok=True)

    backup_dir = os.path.join(base_dir, ".backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"change_{change_id}_{int(datetime.now(UTC).timestamp())}.bak")

    original_code = row["original_code"] or ""
    generated_code = row["generated_code"] or ""
    if not generated_code.strip():
        latest_attempt = get_latest_attempt(change_id)
        generated_code = (latest_attempt or {}).get("generated_code", "")

    if os.path.exists(target_path):
        shutil.copyfile(target_path, backup_path)
    else:
        with open(backup_path, "w", encoding="utf-8") as handle:
            handle.write(original_code)

    try:
        with open(target_path, "w", encoding="utf-8") as handle:
            handle.write(generated_code)
    except OSError as exc:
        rollback_change(backup_path, target_path)
        return False, f"Apply failed and rollback executed: {exc}"

    update_status(change_id, "ACCEPTED")
    log_event("CHANGE_APPLIED", {"target_path": target_path, "backup_path": backup_path}, change_id=change_id)
    return True, f"Applied change to {target_path}. Backup saved at {backup_path}"
