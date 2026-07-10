"""
Marrow — Database Models (Persistence Layer)

Raw sqlite3 with no ORM overhead — optimized for the lightweight,
single-process architecture of the hackathon deployment.

Schema:
    scans            – One row per correlation run. Stores aggregate
                       metrics (cost, risk) and the executive summary.
    recommendations  – One row per resource-level action generated
                       by the LLM reasoner (or deterministic fallback).
                       Linked to scans via foreign key.

Workflow:
    Phase 1 (Correlator)  → save_scan()              → creates scan row
    Phase 2 (Reasoner)    → save_recommendations()   → populates actions
    Phase 2 (Reasoner)    → update_scan_summary()     → attaches executive summary
    Dashboard             → get_latest_scan() + get_recommendations()
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from app.config import Config


def _get_db_path() -> str:
    """Return a clean file path for sqlite3.connect(), stripping any URI prefix."""
    path = Config.DB_PATH
    if path and path.startswith("sqlite:///"):
        path = path.replace("sqlite:///", "", 1)
    return path


def get_connection() -> sqlite3.Connection:
    """Open a connection with row_factory set for dict-like access.

    Uses sqlite3.Row so that columns can be accessed by name,
    and enables foreign key enforcement for referential integrity.
    """
    conn = sqlite3.connect(_get_db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT    NOT NULL,
                resource_count  INTEGER NOT NULL,
                total_monthly_cost  REAL NOT NULL,
                total_risk_score    INTEGER NOT NULL,
                executive_summary   TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id             INTEGER NOT NULL,
                resource_id         TEXT    NOT NULL,
                action              TEXT    NOT NULL DEFAULT '',
                monthly_savings_usd REAL    NOT NULL DEFAULT 0.0,
                annual_savings_usd  REAL    NOT NULL DEFAULT 0.0,
                risk_reduction      TEXT    NOT NULL DEFAULT '',
                priority_score      INTEGER NOT NULL DEFAULT 0,
                confidence          INTEGER NOT NULL DEFAULT 100,
                justification       TEXT    NOT NULL DEFAULT '',
                FOREIGN KEY (scan_id) REFERENCES scans(id)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_scan(correlated_data: list[dict]) -> int:
    """Insert a scan row from correlated resource data. Returns scan_id.

    This is the first write in the two-phase pipeline:
      1. save_scan()            → aggregate metrics (this function)
      2. save_recommendations() → per-resource LLM actions (called later)

    The separation allows the correlator to persist results immediately,
    even if the LLM reasoner times out or falls back to deterministic mode.
    """
    resource_count = len(correlated_data)
    total_monthly_cost = sum(r["monthly_cost_usd"] for r in correlated_data)
    total_risk_score = sum(r["total_risk_score"] for r in correlated_data)
    timestamp = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO scans (timestamp, resource_count, total_monthly_cost, total_risk_score)
            VALUES (?, ?, ?, ?)
            """,
            (timestamp, resource_count, total_monthly_cost, total_risk_score),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def update_scan_summary(scan_id: int, summary: str) -> None:
    """Update the executive summary for an existing scan."""
    conn = get_connection()
    try:
        conn.execute("UPDATE scans SET executive_summary = ? WHERE id = ?", (summary, scan_id))
        conn.commit()
    finally:
        conn.close()


def save_recommendations(scan_id: int, recommendations: list[dict]) -> None:
    """Bulk-insert recommendations for a scan. Called by Phase 3 reasoner."""
    conn = get_connection()
    try:
        conn.executemany(
            """
            INSERT INTO recommendations
                (scan_id, resource_id, action, monthly_savings_usd,
                 annual_savings_usd, risk_reduction, priority_score, confidence, justification)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    scan_id,
                    r["resource_id"],
                    r.get("action", ""),
                    r.get("monthly_savings_usd", 0.0),
                    r.get("annual_savings_usd", 0.0),
                    r.get("risk_reduction", ""),
                    r.get("priority_score", 0),
                    r.get("confidence", 100),
                    r.get("justification", ""),
                )
                for r in recommendations
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_scan() -> dict | None:
    """Return the most recent scan row as a dict, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_scan_history() -> list[dict]:
    """Return all scans ordered by most recent first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM scans ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_recommendations(scan_id: int) -> list[dict]:
    """Return all recommendations for a given scan_id."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM recommendations WHERE scan_id = ? ORDER BY priority_score DESC",
            (scan_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
