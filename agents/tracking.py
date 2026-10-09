"""
Agent 8: Tracking Agent
Manages application lifecycle.
"""

import csv
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)


class TrackingAgent:
    """Manages application lifecycle."""

    def __init__(self, output_file: str = "out.csv") -> None:
        self.output_file = output_file

    def track(self, job_id: str, title: str, company: str,
              result: bool, attempted: bool = True) -> None:
        """Track an application."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = [timestamp, job_id, title, company,
               attempted, result]
        with open(self.output_file, "a+", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)
        log.info(f"Tracked: {title} @ {company} "
                 f"({'applied' if result else 'failed'})")

    def get_recent(self, days: int = 2) -> list[str]:
        """Get recently applied job IDs."""
        if not os.path.exists(self.output_file):
            return []
        try:
            df = pd.read_csv(
                self.output_file,
                header=None,
                names=["timestamp", "jobID", "job",
                       "company", "attempted", "result"],
                lineterminator="\n",
                encoding="utf-8",
            )
            df["timestamp"] = pd.to_datetime(
                df["timestamp"], format="%Y-%m-%d %H:%M:%S"
            )
            df = df[
                df["timestamp"]
                > (datetime.now() - timedelta(days=days))
            ]
            return list(df.jobID)
        except Exception as e:
            log.error(f"Failed to get recent: {e}")
            return []

    def get_stats(self) -> dict:
        """Get application statistics."""
        if not os.path.exists(self.output_file):
            return {}
        try:
            df = pd.read_csv(
                self.output_file,
                header=None,
                names=["timestamp", "jobID", "job",
                       "company", "attempted", "result"],
                lineterminator="\n",
                encoding="utf-8",
            )
            total = len(df)
            applied = df["result"].sum() if "result" in df else 0
            return {
                "total": total,
                "applied": applied,
                "failed": total - applied,
                "rate": applied / total if total > 0 else 0,
            }
        except Exception as e:
            log.error(f"Failed to get stats: {e}")
            return {}

    def update_status(self, job_id: str, status: str) -> None:
        """Update application status (applied, interview, offer, rejected)."""
        if not os.path.exists(self.output_file):
            return
        try:
            df = pd.read_csv(
                self.output_file,
                header=None,
                names=["timestamp", "jobID", "job",
                       "company", "attempted", "result"],
                lineterminator="\n",
                encoding="utf-8",
            )
            mask = df["jobID"] == job_id
            if mask.any():
                df.loc[mask, "status"] = status
                df.to_csv(
                    self.output_file, index=False,
                    header=False, encoding="utf-8"
                )
                log.info(f"Updated {job_id} to {status}")
        except Exception as e:
            log.error(f"Failed to update status: {e}")

    def get_pending(self) -> list[dict]:
        """Get pending applications needing follow-up."""
        if not os.path.exists(self.output_file):
            return []
        try:
            df = pd.read_csv(
                self.output_file,
                header=None,
                names=["timestamp", "jobID", "job",
                       "company", "attempted", "result"],
                lineterminator="\n",
                encoding="utf-8",
            )
            pending = df[df["result"] == True]
            return pending.to_dict("records")
        except Exception:
            return []