"""
Agent 4: Resume Intelligence Agent
Optimizes resume against specific job descriptions with three personas.
"""

import logging
import os
from typing import Optional

from ai_agent import Job, ai_call

log = logging.getLogger(__name__)


class ResumeIntelligenceAgent:
    """Optimizes resume against a specific JD using three evaluation personas."""

    def __init__(self, resume_path: str = "") -> None:
        self.resume_path = resume_path
        self.resume_text = self._load_resume(resume_path)

    def _load_resume(self, path: str) -> str:
        if not path or not os.path.exists(path):
            log.warning(f"Resume not found: {path}")
            return ""

        # If it's a text file, read directly
        if path.endswith('.txt'):
            try:
                with open(path, 'r') as f:
                    return f.read().strip()
            except Exception:
                pass

        # Otherwise try pdftotext for PDFs
        try:
            import subprocess
            result = subprocess.run(
                ["pdftotext", path, "-"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        log.warning(f"Could not extract text from {path}")
        return ""

    def evaluate(self, job: Job, provider: str = "both") -> dict:
        """Run all three persona evaluations and return scores."""
        recruiter_score = self._recruiter_persona(job, provider)
        hm_score = self._hiring_manager_persona(job, provider)
        ats_score = self._ats_evaluator(job, provider)

        # Merge scores into a composite score
        composite = (recruiter_score * 0.3 + hm_score * 0.4 + ats_score * 0.3)

        return {
            "recruiter": recruiter_score,
            "hiring_manager": hm_score,
            "ats": ats_score,
            "composite": composite,
        }

    def optimize(self, job: Job, provider: str = "both") -> str:
        """Optimize resume for a specific job using all three personas."""
        evaluations = self.evaluate(job, provider)
        composite = evaluations["composite"]

        log.info(f"Resume evaluation for {job.title}: "
                 f"recruiter={evaluations['recruiter']:.2f}, "
                 f"hm={evaluations['hiring_manager']:.2f}, "
                 f"ats={evaluations['ats']:.2f}, "
                 f"composite={composite:.2f}")

        # Generate optimized resume
        prompt = [
            {"role": "system", "content":
                "You are a resume optimizer. Rewrite the resume highlights "
                "to match the job description. Use the same format as the "
                "input resume. Focus on relevant skills and achievements."},
            {"role": "user", "content": self._build_optimize_prompt(job)},
        ]
        result = ai_call(prompt, provider=provider)
        job.resume = result or self.resume_text
        return job.resume

    # ─── Persona 1: Senior Technical Recruiter ───────────

    def _recruiter_persona(self, job: Job, provider: str) -> float:
        """Evaluate from a senior technical recruiter's perspective."""
        prompt = [
            {"role": "system", "content":
                "You are a senior technical recruiter. Evaluate how well "
                "a candidate's resume matches a job description. "
                "Score 0.0-1.0 based on: relevance, experience level, "
                "skills match, and cultural fit. Return only a number."},
            {"role": "user", "content": self._build_persona_prompt(
                job, "senior technical recruiter")},
        ]
        result = ai_call(prompt, provider=provider)
        try:
            return float(result.strip().split()[-1])
        except (ValueError, IndexError):
            return 0.0

    # ─── Persona 2: Hiring Manager ───────────────────────

    def _hiring_manager_persona(self, job: Job, provider: str) -> float:
        """Evaluate from a hiring manager's perspective."""
        prompt = [
            {"role": "system", "content":
                "You are a hiring manager. Evaluate a candidate's resume "
                "for a specific role. Score 0.0-1.0 based on: technical "
                "skills, project experience, achievements, and potential "
                "to deliver value. Return only a number."},
            {"role": "user", "content": self._build_persona_prompt(
                job, "hiring manager")},
        ]
        result = ai_call(prompt, provider=provider)
        try:
            return float(result.strip().split()[-1])
        except (ValueError, IndexError):
            return 0.0

    # ─── Persona 3: ATS Evaluator ────────────────────────

    def _ats_evaluator(self, job: Job, provider: str) -> float:
        """Evaluate resume optimization for ATS systems."""
        prompt = [
            {"role": "system", "content":
                "You are an ATS (Applicant Tracking System) evaluator. "
                "Check if a resume would pass ATS screening for a job. "
                "Score 0.0-1.0 based on: keyword match, format "
                "compatibility, section structure, and clarity. "
                "Return only a number."},
            {"role": "user", "content": self._build_persona_prompt(
                job, "ATS evaluator")},
        ]
        result = ai_call(prompt, provider=provider)
        try:
            return float(result.strip().split()[-1])
        except (ValueError, IndexError):
            return 0.0

    # ─── Shared helpers ─────────────────────────────────

    def _build_optimize_prompt(self, job: Job) -> str:
        return (
            f"Job: {job.title} at {job.company}\n"
            f"Description: {job.description}\n\n"
            f"Resume:\n{self.resume_text}\n\n"
            f"Optimize the resume highlights for this job:"
        )

    def _build_persona_prompt(self, job: Job, persona: str) -> str:
        return (
            f"Job: {job.title} at {job.company}\n"
            f"Description: {job.description}\n\n"
            f"Resume:\n{self.resume_text}\n\n"
            f"As a {persona}, score this match 0.0-1.0:"
        )