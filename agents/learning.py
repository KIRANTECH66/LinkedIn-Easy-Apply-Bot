"""
Agent 9: Learning Agent
Learns from outcomes and optimizes future behavior.
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

LEARNING_FILE = "learning.json"


class LearningAgent:
    """Learns from outcomes and optimizes future behavior."""

    def __init__(self, learning_file: str = LEARNING_FILE,
                 output_file: str = "out.csv") -> None:
        self.learning_file = learning_file
        self.output_file = output_file
        self.insights = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.learning_file):
            try:
                with open(self.learning_file) as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"Failed to load learning: {e}")
        return self._default_insights()

    def _default_insights(self) -> dict:
        return {
            "company_success_rate": {},
            "role_success_rate": {},
            "location_success_rate": {},
            "keywords_success": {},
            "total_applied": 0,
            "total_interviews": 0,
            "total_offers": 0,
            "total_rejections": 0,
            "last_updated": "",
        }

    def save(self) -> None:
        with open(self.learning_file, "w") as f:
            json.dump(self.insights, f, indent=2)
        log.info(f"Learning saved to {self.learning_file}")

    def learn_from_outcomes(self) -> None:
        """Learn from application outcomes in output CSV."""
        if not os.path.exists(self.output_file):
            return
        try:
            df = pd.read_csv(
                self.output_file,
                header=None,
                names=["timestamp", "jobID", "job",
                       "company", "attempted", "result"],
                skiprows=1,  # Skip header row
                lineterminator="\n",
                encoding="utf-8",
            )

            # Company success rates
            company_stats = defaultdict(lambda: {"applied": 0,
                                                  "success": 0})
            for _, row in df.iterrows():
                company = row.get("company", "unknown")
                company_stats[company]["applied"] += 1
                if row.get("result"):
                    company_stats[company]["success"] += 1

            for company, stats in company_stats.items():
                rate = (stats["success"] / stats["applied"]
                        if stats["applied"] > 0 else 0)
                self.insights["company_success_rate"][
                    company
                ] = round(rate, 2)

            # Role success rates
            role_stats = defaultdict(lambda: {"applied": 0,
                                               "success": 0})
            for _, row in df.iterrows():
                role = row.get("job", "unknown")
                role_stats[role]["applied"] += 1
                if row.get("result"):
                    role_stats[role]["success"] += 1

            for role, stats in role_stats.items():
                rate = (stats["success"] / stats["applied"]
                        if stats["applied"] > 0 else 0)
                self.insights["role_success_rate"][
                    role
                ] = round(rate, 2)

            self.insights["total_applied"] = len(df)
            self.insights["total_interviews"] = len(
                df[df["status"] == "interview"]
            ) if "status" in df.columns else 0
            self.insights["total_offers"] = len(
                df[df["status"] == "offer"]
            ) if "status" in df.columns else 0
            self.insights["total_rejections"] = len(
                df[df["status"] == "rejected"]
            ) if "status" in df.columns else 0
            self.insights["last_updated"] = datetime.now().isoformat()

            self.save()
        except Exception as e:
            log.error(f"Failed to learn from outcomes: {e}")

    def get_company_recommendation(self, company: str) -> float:
        """Get success rate for a company."""
        return self.insights.get(
            "company_success_rate", {}
        ).get(company, 0.5)

    def get_role_recommendation(self, role: str) -> float:
        """Get success rate for a role."""
        return self.insights.get(
            "role_success_rate", {}
        ).get(role, 0.5)

    def should_apply(self, company: str, role: str) -> bool:
        """Decide whether to apply based on learned insights."""
        company_rate = self.get_company_recommendation(company)
        role_rate = self.get_role_recommendation(role)
        # Apply if either company or role has decent success rate
        return company_rate > 0.3 or role_rate > 0.3

    def get_keywords_for_role(self, role: str) -> list[str]:
        """Get keywords that worked for a role."""
        keywords = self.insights.get("keywords_success", {})
        sorted_kw = sorted(keywords.items(),
                           key=lambda x: x[1], reverse=True)
        return [kw for kw, rate in sorted_kw if rate > 0.5]

    def update_keyword(self, keyword: str, success: bool) -> None:
        """Update keyword success rate."""
        keywords = self.insights.get("keywords_success", {})
        if keyword not in keywords:
            keywords[keyword] = {"success": 0, "total": 0}
        keywords[keyword]["total"] += 1
        if success:
            keywords[keyword]["success"] += 1
        rate = (keywords[keyword]["success"]
                / keywords[keyword]["total"])
        keywords[keyword] = round(rate, 2)
        self.insights["keywords_success"] = keywords
        self.save()