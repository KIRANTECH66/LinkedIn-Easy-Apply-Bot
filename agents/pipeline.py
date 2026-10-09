"""
Multi-Agent Orchestration Pipeline

Instantiates and connects all agents for the full job-application
lifecycle.  Wraps existing agent classes so they can be driven by the
Orchestrator without modifying their internals.

Usage:
    from agents.pipeline import build_pipeline

    pipeline = build_pipeline(browser, wait, ai_config, resume_path="...")
    ctx = AgentContext(job_ids=["job1"], metadata={"position": "...", "location": "..."})
    result = pipeline.run(ctx)
    pipeline.run_job_loop(ctx)
"""

from __future__ import annotations

import logging
from typing import Callable

from .agent import AgentContext, AgentResult, BaseAgent
from .orchestrator import Orchestrator

log = logging.getLogger(__name__)


def _make_profile_runner(profile_agent) -> Callable[[AgentContext], AgentResult]:
    def run(ctx: AgentContext) -> AgentResult:
        profile = profile_agent.get()
        ctx.profile.update(profile)
        ctx.metadata["profile.skills"] = profile.get("skills", [])
        ctx.metadata["profile.experience_years"] = profile.get("experience_years", 0)
        return AgentResult(
            success=True,
            data={"skills": profile.get("skills", []), "experience": profile.get("experience_years", 0)},
        )
    return run


def build_pipeline(browser, wait, ai_config: dict,
                   resume_path: str = "",
                   personal_info: dict | None = None,
                   uploads: dict | None = None) -> Orchestrator:
    """
    Assemble the full agent pipeline and return an Orchestrator instance.

    All agents receive the shared browser/wait through their context
    metadata so the orchestrator can thread them through without
    changing the agents' existing interfaces.
    """
    from ai_agent import AgentConfig
    from .profile_agent import ProfileAgent
    from .job_discovery import JobDiscoveryAgent
    from .job_matching import JobMatchingAgent
    from .resume_intelligence import ResumeIntelligenceAgent
    from .application import ApplicationAgent
    from .question import QuestionAgent
    from .approval import ApprovalAgent
    from .tracking import TrackingAgent
    from .learning import LearningAgent

    config = AgentConfig(
        provider=ai_config.get("provider", "both"),
        model=ai_config.get("model", "gpt-4o"),
        anthropic_model=ai_config.get("anthropic_model", "claude-sonnet-4"),
        threshold=ai_config.get("scoring_threshold", 0.7),
        max_jobs=ai_config.get("max_jobs_per_run", 20),
        batch_size=ai_config.get("batch_size", 10),
        human_approval=ai_config.get("human_approval", False),
        review_file=ai_config.get("review_file", "review_batch.md"),
        timeout_minutes=ai_config.get("api_timeout_minutes", 10),
        recency_priority=ai_config.get("recency_priority", True),
    )

    pipeline = Orchestrator(name="linkedin-easy-apply")

    # Embed browser/wait/ui into context metadata so agents can access them.
    shared = {
        "browser": browser,
        "wait": wait,
        "personal_info": personal_info or {},
        "uploads": uploads or {},
    }

    # ── Agent 1: Profile Agent ────────────────────────────────────
    profile = ProfileAgent(config={"skills": []})
    pipeline.add_agent(profile.name, _make_profile_runner(profile))

    # ── Agent 2: Job Discovery Agent ──────────────────────────────
    def discovery_run(ctx: AgentContext) -> AgentResult:
        position = ctx.metadata.get("position", "")
        location = ctx.metadata.get("location", "")
        max_pages = ctx.metadata.get("max_pages", 3)
        discovery = JobDiscoveryAgent(browser, wait)
        jobs = discovery.discover(position, location, max_pages)
        for job in jobs:
            ctx.add_job(job.job_id, {
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "description": job.description,
                "source": "linkedin",
            })
        return AgentResult(success=True, data={"discovered_count": len(jobs)})
    pipeline.add_agent("job_discovery", discovery_run)

    # ── Agent 3: Job Matching Agent ───────────────────────────────
    matching = JobMatchingAgent(config)

    def matching_run(ctx: AgentContext) -> AgentResult:
        if not ctx.job_ids:
            return AgentResult(success=True, message="No jobs to score")
        jobs = []
        for jid in ctx.job_ids:
            jd = ctx.jobs.get(jid, {})
            jobs.append(type("Job", (), jd)())
        scored = matching.match(jobs, ctx.profile, provider=config.provider)
        for job in scored:
            ctx.set_score(job.job_id, job.score)
            ctx.set_decision(job.job_id, "approved" if job.score >= config.threshold else "skipped")
        return AgentResult(
            success=True,
            data={"scored_count": len(scored), "top_jobs": [j.job_id for j in scored[:config.batch_size]]},
        )
    pipeline.add_agent("job_matching", matching_run)

    # ── Agent 4: Resume Intelligence Agent ────────────────────────
    resume_agent = ResumeIntelligenceAgent(resume_path)

    def resume_run(ctx: AgentContext) -> AgentResult:
        if not ctx.job_ids:
            return AgentResult(success=True, message="No jobs to evaluate")
        for jid in ctx.job_ids:
            jd = ctx.jobs.get(jid, {})
            if not jd:
                continue
            job = type("Job", (), jd)()
            evaluations = resume_agent.evaluate(job, provider=config.provider)
            ctx.artifacts[jid] = {
                "recruiter_score": evaluations.get("recruiter", 0.0),
                "hiring_manager_score": evaluations.get("hiring_manager", 0.0),
                "ats_score": evaluations.get("ats", 0.0),
                "composite_score": evaluations.get("composite", 0.0),
            }
            ctx.set_score(jid, evaluations.get("composite", ctx.scores.get(jid, 0.0)))
            # Customize resume for this job
            optimized = resume_agent.optimize(job, provider=config.provider)
            ctx.artifacts[jid]["optimized_resume"] = optimized
        return AgentResult(success=True)
    pipeline.add_agent("resume_intelligence", resume_run)

    # ── Agent 5: Approval Agent (decision gate) ────────────────────
    approval = ApprovalAgent(
        review_file=config.review_file,
        human_approval=config.human_approval,
        timeout_minutes=config.timeout_minutes,
    )

    def approval_run(ctx: AgentContext) -> AgentResult:
        approved, skipped = [], []
        for jid in ctx.job_ids:
            score = ctx.scores.get(jid, 0.0)
            artifact = ctx.artifacts.get(jid, {})
            composite = artifact.get("composite_score", score)
            decision = "approved" if composite >= config.threshold else "skipped"
            ctx.set_decision(jid, decision)
            if decision == "approved":
                approved.append(jid)
            else:
                skipped.append(jid)
        ctx.metadata["approval.approved"] = approved
        ctx.metadata["approval.skipped"] = skipped
        return AgentResult(success=True, data={"approved": approved, "skipped": skipped})
    pipeline.add_agent("approval", approval_run)

    # ── Agent 6: Application Agent ─────────────────────────────────
    application = ApplicationAgent(browser, wait, shared.get("personal_info", {}), uploads)

    def application_run(ctx: AgentContext) -> AgentResult:
        results = {}
        for jid in ctx.job_ids:
            if ctx.decisions.get(jid) != "approved":
                results[jid] = False
                continue
            jd = ctx.jobs.get(jid, {})
            from ai_agent import Job
            job = Job(
                job_id=jid,
                title=jd.get("title", ""),
                company=jd.get("company", ""),
                location=jd.get("location", ""),
                description=jd.get("description", ""),
            )
            # Use the bot's existing apply_to_job logic via a bridge
            result = application.apply(job, lambda _: True)
            results[jid] = result
            ctx.set_result(jid, result)
        return AgentResult(success=True, data={"applied_count": sum(results.values())})
    pipeline.add_agent("application", application_run)

    # ── Agent 7: Question Agent ────────────────────────────────────
    question = QuestionAgent("qa.csv")

    def question_run(ctx: AgentContext) -> AgentResult:
        # Process any form questions that need answering
        for jid in ctx.job_ids:
            application.process_questions()
        return AgentResult(success=True)
    pipeline.add_agent("question", question_run)

    # ── Agent 8: Tracking Agent ─────────────────────────────────────
    tracking = TrackingAgent("output.csv")

    def tracking_run(ctx: AgentContext) -> AgentResult:
        applied = sum(1 for v in ctx.results.values() if v)
        for jid, result in ctx.results.items():
            jd = ctx.jobs.get(jid, {})
            tracking.track(jid, jd.get("title", ""), jd.get("company", ""), result, attempted=True)
        return AgentResult(success=True, data={"applied": applied})
    pipeline.add_agent("tracking", tracking_run)

    # ── Agent 9: Learning Agent ────────────────────────────────────
    learning = LearningAgent("learning.json", "output.csv")

    def learning_run(ctx: AgentContext) -> AgentResult:
        learning.learn_from_outcomes()
        return AgentResult(success=True)
    pipeline.add_agent("learning", learning_run)

    return pipeline