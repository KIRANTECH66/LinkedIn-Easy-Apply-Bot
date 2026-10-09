"""
Job Database Agent
Canonical representation of discovered and evaluated jobs.
Provides a unified store for the entire pipeline.
"""

import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    company TEXT,
    title TEXT,
    location TEXT,
    description TEXT,
    requirements TEXT,
    source TEXT,
    url TEXT,
    salary TEXT,
    match_score REAL,
    recruiter_score REAL,
    hiring_manager_score REAL,
    ats_score REAL,
    composite_score REAL,
    resume_version INTEGER DEFAULT 1,
    resume_text TEXT,
    cover_letter TEXT,
    decision TEXT,
    decision_reason TEXT,
    status TEXT,  -- pending, applied, interview, offer, rejected
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_timestamp TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_decision
    ON jobs(decision);
CREATE INDEX IF NOT EXISTS idx_jobs_status
    ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_company
    ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_match_score
    ON jobs(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at
    ON jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS application_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    applied_timestamp TIMESTAMP,
    outcome TEXT,  -- applied, failed, skipped
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);
"""


class JobDatabase:
    """Canonical job store for the agentic pipeline."""

    def __init__(self, db_path: str = "jobs.db") -> None:
        self.db_path = Path(db_path)
        self._connection = None
        self._create_schema()

    def _create_schema(self) -> None:
        with self.get_connection() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(str(self.db_path))
            self._connection.row_factory = sqlite3.Row
            log.info(f"Job database opened: {self.db_path}")
        return self._connection

    def add_job(self, job_id: str, company: str, title: str,
                location: str, description: str = "",
                source: str = "linkedin", url: str = "",
                salary: str = "", decision: str = "pending",
                decision_reason: str = "") -> None:
        """Add a newly discovered job to the canonical store."""
        sql = """
        INSERT INTO jobs (
            job_id, company, title, location, description,
            requirements, source, url, salary,
            match_score, recruiter_score, hiring_manager_score,
            ats_score, composite_score, resume_version,
            resume_text, cover_letter, decision, decision_reason,
            status, created_at, updated_at, applied_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT job_id FROM jobs WHERE job_id = ?", (job_id,)
            )
            if cursor.fetchone():
                # Job exists, update in place
                self.update_job(
                    job_id, title=title, company=company,
                    location=location, description=description,
                    url=url, salary=salary, decision=decision,
                    decision_reason=decision_reason,
                )
            else:
                conn.execute(sql, (
                    job_id, company, title, location, description,
                    "", source, url, salary,
                    None, None, None, None, None,
                    None, None, None, decision, decision_reason,
                    "pending", datetime.now().isoformat(),
                    datetime.now().isoformat(), None,
                ))
            conn.commit()
        log.info(f"Job stored: {job_id} — {title} @ {company}")

    def update_job(self, job_id: str, **kwargs: Any) -> None:
        """Update an existing job record with new fields."""
        allowed_fields = {
            "company", "title", "location", "description", "requirements",
            "source", "url", "salary", "match_score", "recruiter_score",
            "hiring_manager_score", "ats_score", "composite_score",
            "resume_version", "resume_text", "cover_letter",
            "decision", "decision_reason", "status", "applied_timestamp",
        }
        update_fields = []
        values = []
        for key, value in kwargs.items():
            if key not in allowed_fields:
                log.warning(f"Skipping unknown field: {key}")
                continue
            if key in ("composite_score", "match_score", "recruiter_score",
                       "hiring_manager_score", "ats_score"):
                if value is not None:
                    value = float(value)
            update_fields.append(f"{key} = ?")
            values.append(value)
        values.append(datetime.now().isoformat())
        values.append(job_id)
        sql = (
            f"UPDATE jobs SET {', '.join(update_fields)}, "
            "updated_at = ? WHERE job_id = ?"
        )
        with self.get_connection() as conn:
            conn.execute(sql, values)
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single job record."""
        sql = "SELECT * FROM jobs WHERE job_id = ?"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (job_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def get_jobs(
        self,
        decision: Optional[str] = None,
        status: Optional[str] = None,
        min_score: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs with optional filters."""
        conditions = []
        params: List[Any] = []

        if decision is not None:
            conditions.append("decision = ?")
            params.append(decision)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if min_score is not None:
            conditions.append("composite_score >= ?")
            params.append(min_score)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT * FROM jobs{where} ORDER BY composite_score DESC"
        if limit:
            sql += f" LIMIT {limit}"

        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_jobs(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get jobs awaiting processing."""
        return self.get_jobs(decision="pending", status="pending", limit=limit)

    def get_decided_jobs(self) -> List[Dict[str, Any]]:
        """Get jobs with a final decision."""
        sql = "SELECT * FROM jobs WHERE decision IN ('approved', 'applied', 'skipped')"
        with self.get_connection() as conn:
            cursor = conn.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

    def get_decision_summary(self) -> Dict[str, int]:
        """Get a summary of decisions."""
        sql = """
        SELECT decision, COUNT(*) as count
        FROM jobs
        GROUP BY decision
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql)
            return {row["decision"]: row["count"] for row in cursor.fetchall()}

    def get_scores_by_company(self) -> Dict[str, Dict[str, float]]:
        """Get composite match score averages per company."""
        sql = """
        SELECT company, AVG(composite_score) as avg_score,
               AVG(match_score) as avg_match, COUNT(*) as n
        FROM jobs
        WHERE composite_score IS NOT NULL
        GROUP BY company
        ORDER BY avg_score DESC
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql)
            return {
                row["company"]: {
                    "avg_score": round(row["avg_score"], 2),
                    "avg_match": round(row["avg_match"], 2),
                    "n": row["n"],
                }
                for row in cursor.fetchall()
            }

    def record_outcome(self, job_id: str, outcome: str,
                       notes: str = "") -> None:
        """Record an application outcome."""
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO application_outcomes (job_id, outcome, notes) "
                "VALUES (?, ?, ?)",
                (job_id, outcome, notes),
            )
            conn.commit()
        log.info(f"Outcome recorded for {job_id}: {outcome}")

    def get_jobs_for_learning(self) -> List[Dict[str, Any]]:
        """Get jobs and outcomes for learning agent."""
        sql = """
        SELECT j.job_id, j.company, j.title, j.decision, j.match_score,
               o.outcome, o.applied_timestamp
        FROM jobs j
        LEFT JOIN application_outcomes o ON j.job_id = o.job_id
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

    def export_to_json(self, path: str = "jobs_export.json") -> None:
        """Export the job database to a JSON file."""
        export_data = []
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")
            for row in cursor.fetchall():
                export_data.append(dict(row))
        with open(path, "w") as f:
            import json
            json.dump(export_data, f, indent=2)
        log.info(f"Job database exported to {path}")

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            log.info("Job database closed")

    def __enter__(self) -> "JobDatabase":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
