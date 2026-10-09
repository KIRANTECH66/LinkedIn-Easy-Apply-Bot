"""
Base agent interface for the multi-agent orchestration loop.

Every agent implements the same contract:
    run(context) -> AgentResult

The orchestrator threads a shared `AgentContext` through the pipeline,
so each agent can read prior decisions and append its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Standard return value from every agent's run()."""

    success: bool
    message: str = ""
    data: dict = field(default_factory=dict)
    # When False, the orchestrator stops the pipeline for this item.
    stop: bool = False


@dataclass
class AgentContext:
    """Shared state threaded through the agentic loop."""

    # The job(s) currently being processed
    job_ids: list = field(default_factory=list)
    # Extracted job data keyed by job_id
    jobs: dict = field(default_factory=dict)
    # Candidate profile (skills, experience, etc.)
    profile: dict = field(default_factory=dict)
    # Per-job decisions: job_id -> "apply" | "skip" | "review"
    decisions: dict = field(default_factory=dict)
    # Per-job scores: job_id -> float
    scores: dict = field(default_factory=dict)
    # Per-job customized artifacts
    artifacts: dict = field(default_factory=dict)
    # Application results: job_id -> bool
    results: dict = field(default_factory=dict)
    # Arbitrary agent-specific metadata
    metadata: dict = field(default_factory=dict)
    # Run-level flags
    should_stop: bool = False

    def add_job(self, job_id: str, job_data: dict | None = None) -> None:
        if job_id not in self.jobs:
            self.jobs[job_id] = job_data or {}
            self.job_ids.append(job_id)

    def set_decision(self, job_id: str, decision: str) -> None:
        self.decisions[job_id] = decision

    def set_score(self, job_id: str, score: float) -> None:
        self.scores[job_id] = score

    def set_result(self, job_id: str, success: bool) -> None:
        self.results[job_id] = success

    def clone_for_job(self, job_id: str) -> "AgentContext":
        """Return a shallow copy scoped to a single job."""
        ctx = AgentContext(
            job_ids=[job_id],
            jobs={job_id: self.jobs.get(job_id, {})},
            profile=self.profile,
            decisions={job_id: self.decisions.get(job_id, "")},
            scores={job_id: self.scores.get(job_id, 0.0)},
            artifacts={job_id: self.artifacts.get(job_id, {})},
            results={job_id: self.results.get(job_id, False)},
            metadata=dict(self.metadata),
        )
        return ctx


class BaseAgent:
    """Abstract base class every orchestration agent inherits from."""

    name: str = "base"

    def __init__(self, name: str | None = None) -> None:
        if name:
            self.name = name
        self.log = logging.getLogger(f"agent.{self.name}")

    def run(self, context: AgentContext) -> AgentResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement run()"
        )

    def can_handle(self, context: AgentContext) -> bool:
        """Return True if this agent should run for the current context."""
        return True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name}>"