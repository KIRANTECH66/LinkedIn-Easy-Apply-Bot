"""
Agent 7: Approval Agent
Human review and authorization.
"""

import logging
import os
import time
from typing import Optional

from ai_agent import Job

log = logging.getLogger(__name__)


class ApprovalAgent:
    """Human review and authorization."""

    def __init__(self, review_file: str = "review_batch.md",
                 human_approval: bool = False,
                 timeout_minutes: int = 10) -> None:
        self.review_file = review_file
        self.human_approval = human_approval
        self.timeout_minutes = timeout_minutes

    def review(self, jobs: list[Job]) -> list[Job]:
        """Review jobs and return approved list."""
        if not self.human_approval:
            return self._auto_approve(jobs)
        return self._review_with_approval(jobs)

    def _auto_approve(self, jobs: list[Job]) -> list[Job]:
        for job in jobs:
            job.approved = True
        log.info(f"Auto-approved {len(jobs)} jobs")
        self._write_review_file(jobs)
        return jobs

    def _review_with_approval(self, jobs: list[Job]) -> list[Job]:
        self._write_review_file(jobs)
        log.info(f"Review file: {self.review_file}")
        log.info(
            f"Waiting {self.timeout_minutes} min for approval..."
        )
        deadline = time.time() + self.timeout_minutes * 60
        while time.time() < deadline:
            time.sleep(10)
            approved = self._read_approvals(jobs)
            if approved:
                return approved
        log.warning("Approval timeout — auto-approving all")
        for job in jobs:
            job.approved = True
        return jobs

    def _write_review_file(self, jobs: list[Job]) -> None:
        lines = ["# Job Review Batch\n",
                 "Edit this file: mark jobs APPROVE or SKIP\n"]
        for i, job in enumerate(jobs):
            lines.append(
                f"## {i+1}. {job.title} @ {job.company} "
                f"(score: {job.score:.2f})\n"
            )
            lines.append(f"Status: APPROVE\n")
            lines.append(
                f"Resume preview: {job.resume[:200]}...\n"
            )
            lines.append(
                f"Cover letter preview: "
                f"{job.cover_letter[:200]}...\n\n"
            )
        with open(self.review_file, "w") as f:
            f.write("\n".join(lines))

    def _read_approvals(self, jobs: list[Job]) -> list[Job]:
        if not os.path.exists(self.review_file):
            return []
        try:
            with open(self.review_file) as f:
                content = f.read()
            approved = []
            for i, job in enumerate(jobs):
                if ("Status: APPROVE" in content
                        or f"{i+1}." in content
                            and "APPROVE" in content):
                    job.approved = True
                    approved.append(job)
                else:
                    job.approved = False
            return approved
        except Exception as e:
            log.error(f"Failed to read approvals: {e}")
            return []

    def approve_job(self, job_id: str) -> None:
        """Approve a specific job by ID."""
        if not os.path.exists(self.review_file):
            return
        try:
            with open(self.review_file) as f:
                content = f.read()
            content = content.replace(
                f"Status: APPROVE", "Status: APPROVED", 1
            )
            with open(self.review_file, "w") as f:
                f.write(content)
        except Exception as e:
            log.error(f"Failed to approve job: {e}")