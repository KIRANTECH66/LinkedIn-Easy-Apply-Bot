"""
Agent 6: Question Agent
Generates and validates application answers.
"""

import logging
from typing import Optional

from ai_agent import Job, ai_call

log = logging.getLogger(__name__)


class QuestionAgent:
    """Generates and validates application answers."""

    def __init__(self, qa_file: str = "qa.csv") -> None:
        self.qa_file = qa_file
        self.answers = {}
        self._load_answers()

    def _load_answers(self) -> None:
        """Load existing Q&A pairs from CSV."""
        try:
            import pandas as pd
            if pd.io.common.file_exists(self.qa_file):
                df = pd.read_csv(self.qa_file)
                for _, row in df.iterrows():
                    self.answers[row["Question"]] = row["Answer"]
        except Exception as e:
            log.error(f"Failed to load Q&A: {e}")

    def answer(self, question: str, job: Optional[Job] = None,
               provider: str = "both") -> str:
        """Generate an answer for a screening question."""
        # Check existing answers first
        if question in self.answers:
            return self.answers[question]

        # Generate new answer via AI
        prompt = [
            {"role": "system", "content":
                "You are an application assistant. Answer screening "
                "questions based on the candidate profile and job "
                "description. Be honest and professional."},
            {"role": "user", "content": self._build_prompt(question, job)},
        ]
        result = ai_call(prompt, provider=provider)
        answer = result.strip() if result else ""

        # Save to Q&A
        self.answers[question] = answer
        self._save_answer(question, answer)

        return answer

    def _build_prompt(self, question: str,
                      job: Optional[Job]) -> str:
        job_info = ""
        if job:
            job_info = (
                f"\nJob: {job.title} at {job.company}\n"
                f"Description: {job.description}"
            )
        return (
            f"Question: {question}{job_info}\n\n"
            f"Provide a concise, honest answer:"
        )

    def _save_answer(self, question: str, answer: str) -> None:
        try:
            import pandas as pd
            new_data = pd.DataFrame({
                "Question": [question], "Answer": [answer]
            })
            new_data.to_csv(
                self.qa_file, mode="a",
                header=False, index=False, encoding="utf-8"
            )
        except Exception as e:
            log.error(f"Failed to save answer: {e}")

    def validate_answer(self, question: str, answer: str) -> bool:
        """Validate an answer is appropriate."""
        if not answer or len(answer) < 3:
            return False
        # Check for generic/unhelpful answers
        generic = ["yes", "no", "n/a", "tbd", "todo"]
        if answer.lower().strip() in generic:
            return False
        return True