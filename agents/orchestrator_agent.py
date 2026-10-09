"""
OrchestratorAgent — adapts existing agents to the BaseAgent contract.

Wraps any existing agent class so it can be used inside the orchestrator
without changing its internal implementation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from .agent import BaseAgent, AgentContext, AgentResult

log = logging.getLogger(__name__)


@dataclass
class OrchestratorAgent(BaseAgent):
    """
    Wraps an existing agent class into a BaseAgent.

    The wrapped agent is called as `agent.run(context)`, but you can also
    provide a raw `run_fn` callback instead of a class.
    """

    name: str = "adapter"
    agent: BaseAgent | None = None
    run_fn: Callable[[AgentContext], AgentResult] | None = None

    def run(self, context: AgentContext) -> AgentResult:
        if self.run_fn:
            return self.run_fn(context)
        if self.agent:
            return self.agent.run(context)
        return AgentResult(success=False, message="No agent or run_fn configured")


# ------------------------------------------------------------------
# Builder helpers for common wrappers
# ------------------------------------------------------------------
def wrap_fn(name: str, fn: Callable[[AgentContext], AgentResult],
            can_handle: Callable[[AgentContext], bool] | None = None) -> OrchestratorAgent:
    """Create an agent from a standalone function."""
    a = OrchestratorAgent(name=name)
    a.run_fn = fn
    if can_handle:
        a.can_handle = can_handle  # type: ignore[method-assign]
    return a


def wrap_method(agent: BaseAgent, method: str) -> OrchestratorAgent:
    """Create an agent that calls a named method on an existing agent."""
    a = OrchestratorAgent(name=agent.name)
    a.agent = agent

    def runner(ctx: AgentContext) -> AgentResult:
        method_obj = getattr(agent, method, None)
        if method_obj is None:
            return AgentResult(success=False, message=f"No method '{method}'")
        return method_obj(ctx)  # type: ignore[operator]

    a.run_fn = runner
    return a