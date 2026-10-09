"""
AI Agent module for intelligent job application.

Flow:
  1. Score jobs against profile (AI)
  2. Customize resume + cover letter per job (AI)
  3. Review / auto-approve batch
  4. Delegate submission to EasyApplyBot
"""

import logging
import os
import re
import time
from typing import Optional
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

# ─── Data structures ───────────────────────────────────────────

@dataclass
class Job:
    job_id: str
    title: str
    company: str
    location: str
    description: str = ""
    score: float = 0.0
    resume: str = ""
    cover_letter: str = ""
    approved: bool = False

@dataclass
class AgentConfig:
    provider: str = "both"
    model: str = "gpt-4o"
    anthropic_model: str = "claude-sonnet-4"
    threshold: float = 0.7
    max_jobs: int = 20
    batch_size: int = 10
    human_approval: bool = False
    review_file: str = "review_batch.md"
    timeout_minutes: int = 10
    recency_priority: bool = True


# ─── Provider helpers ──────────────────────────────────────────

def _load_env() -> dict:
    """Load variables from .env if present, falling back to the OS environment.

    Keys read from the process environment (e.g. ANTHROPIC_AUTH_TOKEN,
    ANTHROPIC_BASE_URL) take precedence over empty values in .env so the
    bot works whether credentials are set via .env or exported in the shell.
    """
    env = dict(os.environ)
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"')
                    # .env only overrides when it actually defines a value
                    if val:
                        env[key] = val
    return env


_ENV = _load_env()


def _openai_call(messages: list, model: str = "gpt-4o") -> str:
    """Call OpenAI chat completions API."""
    api_key = _ENV.get("OPENAI_API_KEY", "")
    if not api_key:
        log.warning("OPENAI_API_KEY not set")
        return ""
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "max_tokens": 2000,
                "temperature": 0.3,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.error(f"OpenAI call failed: {e}")
        return ""


def _anthropic_call(messages: list, model: str = "claude-sonnet-4") -> str:
    """Call Anthropic Messages API."""
    api_key = _ENV.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY not set")
        return ""
    # Use custom base URL from .env if set
    base_url = _ENV.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    # Use custom model from .env if set
    model = _ENV.get("ANTHROPIC_MODEL", model)
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 2000,
                "temperature": 0.3,
                "messages": messages,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
    except Exception as e:
        log.error(f"Anthropic call failed: {e}")
        return ""


def ai_call(messages: list, provider: str = "both", model: str = "gpt-4o",
            anthropic_model: str = "claude-sonnet-4") -> str:
    """Call AI provider with fallback."""
    if provider in ("openai", "both"):
        result = _openai_call(messages, model)
        if result:
            return result
    if provider in ("anthropic", "both"):
        result = _anthropic_call(messages, anthropic_model)
        if result:
            return result
    return ""


# ─── Agent logic ───────────────────────────────────────────────

class AIAgent:
    """Agentic pipeline: score → customize → review → submit."""

    def __init__(self, config: AgentConfig, resume_text: str = "") -> None:
        self.config = config
        self.resume_text = resume_text

    def score_jobs(self, jobs: list[Job], provider: str = "both") -> list[Job]:
        """Score each job against the profile; return sorted by score."""
        scored = []
        for job in jobs:
            score = self._score_single(job, provider)
            job.score = score
            if score >= self.config.threshold:
                scored.append(job)
                log.info(f"Job {job.job_id}: {job.title} @ {job.company} — score {score:.2f}")
            else:
                log.info(f"Job {job.job_id}: {job.title} @ {job.company} — skipped (score {score:.2f})")
        scored.sort(key=lambda j: j.score, reverse=True)
        return scored[:self.config.max_jobs]

    def extract_jobs_from_search(self, page_source: str, position: str = "",
                                 location: str = "") -> list[Job]:
        """Parse LinkedIn search results HTML into Job objects."""
        from bs4 import BeautifulSoup
        import re

        soup = BeautifulSoup(page_source, "lxml")
        jobs = []
        seen = set()

        # LinkedIn job cards: div[data-job-id]
        cards = soup.select('div[data-job-id]')
        for card in cards:
            job_id = card.get("data-job-id")
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)

            title_el = card.select_one("h3.job-search-results__job-title")
            title = title_el.get_text(strip=True) if title_el else ""

            company_el = card.select_one("h4.job-search-results__company-name")
            company = company_el.get_text(strip=True) if company_el else ""

            loc_el = card.select_one("span.job-search-results__location")
            loc = loc_el.get_text(strip=True) if loc_el else location

            date_el = card.select_one("span.job-search-results__posted-date")
            posted = date_el.get_text(strip=True) if date_el else ""

            jobs.append(Job(
                job_id=job_id,
                title=title,
                company=company,
                location=loc,
                description=posted,  # store posting date in description for now
            ))

        log.info(f"Extracted {len(jobs)} jobs from search results")
        return jobs

    def score_and_filter(self, jobs: list[Job], provider: str = "both") -> list[Job]:
        """Score jobs, filter by threshold, add recency bonus, sort."""
        scored = []
        for job in jobs:
            score = self._score_single(job, provider)
            job.score = score
            if score < self.config.threshold:
                log.info(f"Job {job.job_id}: {job.title} @ {job.company} — skipped (score {score:.2f})")
                continue
            if self.config.recency_priority:
                score = self._apply_recency_bonus(score, job.description)
                job.score = score
            scored.append(job)
            log.info(f"Job {job.job_id}: {job.title} @ {job.company} — score {score:.2f}")
        scored.sort(key=lambda j: j.score, reverse=True)
        return scored[:self.config.max_jobs]

    def _apply_recency_bonus(self, score: float, posted_text: str) -> float:
        """Add recency bonus: 24h +0.1, 7d +0.05, 30d +0.0."""
        text = posted_text.lower()
        if "just" in text or "now" in text or "today" in text:
            return min(score + 0.1, 1.0)
        if "hour" in text or "minute" in text:
            return min(score + 0.1, 1.0)
        if "day" in text:
            try:
                days = int(re.search(r"(\d+)", posted_text).group(1))
                if days <= 1:
                    return min(score + 0.1, 1.0)
                if days <= 7:
                    return min(score + 0.05, 1.0)
            except Exception:
                pass
        return score

    def rank_jobs(self, jobs: list[Job]) -> list[Job]:
        """Rank jobs by score, apply diversity filter, effort priority."""
        if not jobs:
            return []

        # Diversity filter: skip if company already in top results
        seen_companies = set()
        ranked = []
        for job in jobs:
            if job.company in seen_companies:
                continue
            seen_companies.add(job.company)
            ranked.append(job)
            if len(ranked) >= self.config.batch_size:
                break

        # Effort priority: Easy Apply > Company site
        ranked.sort(key=lambda j: (
            0 if "easy apply" in j.title.lower() else 1,
            -j.score
        ))

        log.info(f"Ranked {len(ranked)} jobs after diversity filter")
        return ranked

    def _score_single(self, job: Job, provider: str) -> float:
        prompt = [
            {"role": "system", "content": "You are a job matching expert. Score 0.0-1.0 how well a candidate matches a job. Return only a number."},
            {"role": "user", "content": f"Job: {job.title} at {job.company}\nDescription: {job.description}\nScore this job 0.0-1.0:"},
        ]
        result = ai_call(prompt, provider=provider)
        try:
            return float(result.strip().split()[-1])
        except (ValueError, IndexError):
            return 0.0

    def customize_resume(self, job: Job, provider: str = "both") -> str:
        """Rewrite resume highlights tailored to the job."""
        prompt = [
            {"role": "system", "content": "You are a resume writer. Rewrite the resume highlights to match the job description. Use the same format as the input resume."},
            {"role": "user", "content": f"Job: {job.title} at {job.company}\nDescription: {job.description}\n\nResume:\n{self.resume_text}\n\nRewrite the resume highlights:"},
        ]
        result = ai_call(prompt, provider=provider)
        job.resume = result or self.resume_text
        return job.resume

    def customize_cover_letter(self, job: Job, provider: str = "both") -> str:
        """Write a tailored cover letter for the job."""
        prompt = [
            {"role": "system", "content": "You are a cover letter writer. Write a concise cover letter tailored to the job description."},
            {"role": "user", "content": f"Job: {job.title} at {job.company}\nDescription: {job.description}\n\nWrite a cover letter:"},
        ]
        result = ai_call(prompt, provider=provider)
        job.cover_letter = result or ""
        return job.cover_letter

    def review_batch(self, jobs: list[Job]) -> list[Job]:
        """Generate review file, wait for approval, return approved jobs."""
        if self.config.human_approval:
            return self._review_with_approval(jobs)
        return self._auto_approve(jobs)

    def _auto_approve(self, jobs: list[Job]) -> list[Job]:
        for job in jobs:
            job.approved = True
        log.info(f"Auto-approved {len(jobs)} jobs")
        self._write_review_file(jobs)
        return jobs

    def _review_with_approval(self, jobs: list[Job]) -> list[Job]:
        self._write_review_file(jobs)
        log.info(f"Review file written: {self.config.review_file}")
        log.info(f"Waiting {self.config.timeout_minutes} min for approval edits...")
        deadline = time.time() + self.config.timeout_minutes * 60
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
        lines = ["# Job Review Batch\n", "Edit this file: mark jobs APPROVE or SKIP\n"]
        for i, job in enumerate(jobs):
            lines.append(f"## {i+1}. {job.title} @ {job.company} (score: {job.score:.2f})\n")
            lines.append(f"Status: APPROVE\n")
            lines.append(f"Resume preview: {job.resume[:200]}...\n")
            lines.append(f"Cover letter preview: {job.cover_letter[:200]}...\n\n")
        with open(self.config.review_file, "w") as f:
            f.write("\n".join(lines))

    def _read_approvals(self, jobs: list[Job]) -> list[Job]:
        if not os.path.exists(self.config.review_file):
            return []
        try:
            with open(self.config.review_file) as f:
                content = f.read()
            approved = []
            for i, job in enumerate(jobs):
                if f"Status: APPROVE" in content or f"{i+1}." in content and "APPROVE" in content:
                    job.approved = True
                    approved.append(job)
                else:
                    job.approved = False
            return approved
        except Exception as e:
            log.error(f"Failed to read approvals: {e}")
            return []
