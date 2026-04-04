import sqlite3
import os

DB_PATH = "data/changes.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requirement_id TEXT,
                file_path TEXT,
                original_code TEXT,
                generated_code TEXT,
                diff TEXT,
                review_comment TEXT,
                status TEXT,
                confidence REAL,
                confidence_explanation TEXT,
                rejection_history TEXT,
                feedback_comments TEXT,
                latest_attempt INTEGER,
                attempts_count INTEGER DEFAULT 0,
                impact_summary TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_id INTEGER NOT NULL,
                attempt_number INTEGER NOT NULL,
                generated_code TEXT,
                diff TEXT,
                review_json TEXT,
                validation_message TEXT,
                status TEXT,
                confidence REAL,
                confidence_explanation TEXT,
                context_json TEXT,
                feedback_used TEXT,
                impact_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(change_id) REFERENCES changes(id)
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_id INTEGER NOT NULL,
                attempt_id INTEGER,
                decision TEXT,
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(change_id) REFERENCES changes(id),
                FOREIGN KEY(attempt_id) REFERENCES attempts(id)
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS impact_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_id INTEGER NOT NULL,
                attempt_id INTEGER,
                impacted_files TEXT,
                impacted_functions TEXT,
                dependency_chain TEXT,
                risk_score REAL,
                summary TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(change_id) REFERENCES changes(id),
                FOREIGN KEY(attempt_id) REFERENCES attempts(id)
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS graph_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_path TEXT,
                graph_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS file_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE,
                language TEXT,
                summary TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                change_id INTEGER,
                attempt_id INTEGER,
                payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS saved_requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_key TEXT UNIQUE,
                source_type TEXT,
                source_label TEXT,
                mode TEXT,
                raw_text TEXT,
                normalized_json TEXT,
                item_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )

        _ensure_column(conn, "changes", "generated_code", "TEXT")
        _ensure_column(conn, "changes", "confidence_explanation", "TEXT")
        _ensure_column(conn, "changes", "latest_attempt", "INTEGER")
        _ensure_column(conn, "changes", "attempts_count", "INTEGER DEFAULT 0")
        _ensure_column(conn, "changes", "impact_summary", "TEXT")
        _ensure_column(conn, "changes", "created_at", "TEXT")
        _ensure_column(conn, "changes", "updated_at", "TEXT")
        _ensure_column(conn, "saved_requirements", "source_type", "TEXT")
        _ensure_column(conn, "saved_requirements", "source_label", "TEXT")
        _ensure_column(conn, "saved_requirements", "mode", "TEXT")
        _ensure_column(conn, "saved_requirements", "raw_text", "TEXT")
        _ensure_column(conn, "saved_requirements", "normalized_json", "TEXT")
        _ensure_column(conn, "saved_requirements", "item_count", "INTEGER DEFAULT 0")
        _ensure_column(conn, "saved_requirements", "created_at", "TEXT")
        _ensure_column(conn, "saved_requirements", "updated_at", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
