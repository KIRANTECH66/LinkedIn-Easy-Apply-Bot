"""
Agent 3: Job Matching Agent
Matches and prioritizes jobs against the candidate profile.
"""

import logging
from typing import Optional

from ai_agent import Job, AgentConfig, ai_call

log = logging.getLogger(__name__)


class JobMatchingAgent:
    """Matches and prioritizes jobs against the candidate profile."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def match(self, jobs: list[Job], profile: dict,
              provider: str = "both") -> list[Job]:
        """Match jobs against profile, score, filter, and rank."""
        scored = []
        for job in jobs:
            score = self._score(job, profile, provider)
            job.score = score
            if score >= self.config.threshold:
                scored.append(job)
                log.info(f"Job {job.job_id}: {job.title} @ {job.company} "
                         f"— match {score:.2f}")
            else:
                log.info(f"Job {job.job_id}: {job.title} @ {job.company} "
                         f"— skipped (match {score:.2f})")

        scored.sort(key=lambda j: j.score, reverse=True)
        return scored[:self.config.max_jobs]

    def _score(self, job: Job, profile: dict, provider: str) -> float:
        prompt = [
            {"role": "system", "content":
                "You are a job matching expert. Score 0.0-1.0 how well a "
                "candidate profile matches a job. Consider skills, experience, "
                "education, location, and role relevance. Return only a number."},
            {"role": "user", "content": self._build_prompt(job, profile)},
        ]
        result = ai_call(prompt, provider=provider)
        try:
            return float(result.strip().split()[-1])
        except (ValueError, IndexError):
            return 0.0

    def _build_prompt(self, job: Job, profile: dict) -> str:
        skills = ", ".join(profile.get("skills", []))
        exp = profile.get("experience_years", 0)
        edu = profile.get("education", "")
        return (
            f"Job: {job.title} at {job.company}\n"
            f"Location: {job.location}\n"
            f"Description: {job.description}\n\n"
            f"Candidate Profile:\n"
            f"Skills: {skills}\n"
            f"Experience: {exp} years\n"
            f"Education: {edu}\n\n"
            f"Score this job 0.0-1.0:"
        )

    def prioritize(self, jobs: list[Job]) -> list[Job]:
        """Prioritize by score, recency, and diversity."""
        # Diversity filter
        seen_companies = set()
        prioritized = []
        for job in jobs:
            if job.company in seen_companies:
                continue
            seen_companies.add(job.company)
            prioritized.append(job)

        # Sort by score desc
        prioritized.sort(key=lambda j: (-j.score, j.job_id))
        return prioritized[:self.config.max_jobs]