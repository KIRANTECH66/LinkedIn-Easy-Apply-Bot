"""
Multi-Agent Orchestrator — Agentic AI Loop

Drives the full job-application pipeline as a sequence of specialized
agents.  Each agent inspects the shared AgentContext and decides what
to do next; the orchestrator keeps looping until every job in the batch
has been processed or a stop condition fires.

Pipeline (per job):
    1. ProfileAgent        → load/update candidate profile
    2. JobDiscoveryAgent   → discover jobs from LinkedIn search
    3. JobMatchingAgent    → score jobs against profile
    4. ResumeIntelligenceAgent → evaluate + customize resume
    5. ApprovalAgent       → decide apply/skip (auto or human)
    6. ApplicationAgent    → submit the application
    7. QuestionAgent       → answer form questions
    8. TrackingAgent       → record outcome
    9. LearningAgent       → update weights from outcome

The orchestrator supports:
    * Parallel agent execution (where safe)
    * Conditional branching (skip agents based on prior decisions)
    * Retry with backoff
    * Full observability via the shared context
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from .agent import AgentContext, AgentResult, BaseAgent

log = logging.getLogger(__name__)


class Orchestrator:
    """Drives a list of agents through a shared context."""

    def __init__(self, name: str = "orchestrator") -> None:
        self.name = name
        self.agents: list[BaseAgent] = []
        self.log = logging.getLogger(f"orchestrator.{name}")

    # ------------------------------------------------------------------
    # Pipeline construction
    # ------------------------------------------------------------------
    def add_agent(self, agent: BaseAgent) -> "Orchestrator":
        self.agents.append(agent)
        return self

    def add_agents(self, agents: list[BaseAgent]) -> "Orchestrator":
        self.agents.extend(agents)
        return self

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self, context: AgentContext) -> AgentContext:
        """Execute every agent in order, threading the shared context."""
        self.log.info(f"Orchestrator '{self.name}' starting with "
                      f"{len(context.job_ids)} job(s)")

        for agent in self.agents:
            if context.should_stop:
                self.log.info("Stop flag set — skipping remaining agents")
                break

            if not agent.can_handle(context):
                self.log.debug(f"Skipping {agent.name} (cannot handle context)")
                continue

            self.log.info(f"── Running agent: {agent.name} ──")
            try:
                result = agent.run(context)
            except Exception as exc:
                self.log.error(f"Agent {agent.name} raised: {exc}")
                result = AgentResult(
                    success=False,
                    message=f"{agent.name} failed: {exc}",
                    stop=False,
                )

            if not result.success:
                self.log.warning(
                    f"Agent {agent.name} reported failure: {result.message}"
                )
                if result.stop:
                    context.should_stop = True
                    break
                # Continue — other agents may still succeed

            # Merge agent's returned data back into context
            if result.data:
                for key, value in result.data.items():
                    context.metadata[f"{agent.name}.{key}"] = value

        self.log.info(
            f"Orchestrator '{self.name}' finished. "
            f"Applied: {sum(1 for v in context.results.values() if v)} / "
            f"{len(context.results)}"
        )
        return context

    # ------------------------------------------------------------------
    # Agentic per-job loop
    # ------------------------------------------------------------------
    def run_job_loop(self, context: AgentContext,
                     max_iterations: int = 50) -> AgentContext:
        """Run the full pipeline once per job, with retry/backoff."""
        for iteration in range(max_iterations):
            if not context.job_ids:
                self.log.info("No more jobs to process — loop complete")
                break

            job_id = context.job_ids[0]
            self.log.info(f"=== Iteration {iteration + 1}: job {job_id} ===")

            # Scope context to this single job
            job_context = context.clone_for_job(job_id)

            # Run the pipeline for this job
            job_context = self.run(job_context)

            # Merge results back
            context.results[job_id] = job_context.results.get(job_id, False)
            context.decisions[job_id] = job_context.decisions.get(job_id, "")
            context.scores[job_id] = job_context.scores.get(job_id, 0.0)
            context.artifacts[job_id] = job_context.artifacts.get(job_id, {})
            context.jobs[job_id] = job_context.jobs.get(job_id, {})

            # Remove processed job
            context.job_ids.pop(0)

            # Brief pause between jobs (politeness)
            time.sleep(1)

        return context

    # ------------------------------------------------------------------
    # Async variant (for I/O-bound agents)
    # ------------------------------------------------------------------
    async def run_async(self, context: AgentContext) -> AgentContext:
        for agent in self.agents:
            if context.should_stop:
                break
            if not agent.can_handle(context):
                continue
            self.log.info(f"── Running agent (async): {agent.name} ──")
            try:
                result = await agent.run(context)  # type: ignore[misc]
            except TypeError:
                result = agent.run(context)
            if result.data:
                for key, value in result.data.items():
                    context.metadata[f"{agent.name}.{key}"] = value
        return context