"""
Agent 1: Profile Agent
Builds and maintains the candidate truth/profile.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

PROFILE_FILE = "profile.json"

DEFAULT_PROFILE = {
    "name": "",
    "email": "",
    "phone": "",
    "location": "",
    "skills": [],
    "experience_years": 0,
    "education": "",
    "certifications": [],
    "salary_expectation": 0,
    "work_authorization": "US Citizen",
    "remote_ok": True,
    "willing_to_relocate": False,
    "preferred_roles": [],
    "preferred_locations": [],
    "blacklist_companies": [],
    "blacklist_titles": [],
}


class ProfileAgent:
    """Builds and maintains the candidate truth/profile."""

    def __init__(self, profile_path: str = None, config: dict = None) -> None:
        self.profile_path = profile_path or PROFILE_FILE
        self.profile = dict(DEFAULT_PROFILE)
        if config:
            self._merge_config(config)
        self._load()

    def _merge_config(self, config: dict) -> None:
        """Merge config.yaml values into profile."""
        if "name" in config:
            self.profile["name"] = config["name"]
        if "email" in config:
            self.profile["email"] = config["email"]
        if "phone_number" in config:
            self.profile["phone"] = config["phone_number"]
        if "salary" in config:
            self.profile["salary_expectation"] = config["salary"]
        if "positions" in config:
            self.profile["preferred_roles"] = config["positions"]
        if "locations" in config:
            self.profile["preferred_locations"] = config["locations"]
        if "blacklist" in config:
            self.profile["blacklist_companies"] = config["blacklist"]
        if "blackListTitles" in config:
            self.profile["blacklist_titles"] = config["blackListTitles"]

    def _load(self) -> None:
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path) as f:
                    data = json.load(f)
                self.profile.update(data)
                log.info(f"Profile loaded from {self.profile_path}")
            except Exception as e:
                log.error(f"Failed to load profile: {e}")
        else:
            log.info("No existing profile found, using defaults")

    def save(self) -> None:
        with open(self.profile_path, "w") as f:
            json.dump(self.profile, f, indent=2)
        log.info(f"Profile saved to {self.profile_path}")

    def get(self) -> dict:
        return dict(self.profile)

    def update(self, updates: dict) -> None:
        self.profile.update(updates)
        self.save()

    def get_skills_str(self) -> str:
        return ", ".join(self.profile.get("skills", []))

    def get_experience_summary(self) -> str:
        exp = self.profile.get("experience_years", 0)
        edu = self.profile.get("education", "")
        return f"{exp} years, {edu}"

    def is_company_blacklisted(self, company: str) -> bool:
        return company.lower() in [c.lower() for c in self.profile.get("blacklist_companies", [])]

    def is_title_blacklisted(self, title: str) -> bool:
        return title.lower() in [t.lower() for t in self.profile.get("blacklist_titles", [])]

    def matches_preferred_role(self, title: str) -> bool:
        preferred = [r.lower() for r in self.profile.get("preferred_roles", [])]
        if not preferred:
            return True
        return any(p in title.lower() for p in preferred)

    def matches_preferred_location(self, location: str) -> bool:
        preferred = [l.lower() for l in self.profile.get("preferred_locations", [])]
        if not preferred:
            return True
        return any(p in location.lower() for p in preferred) or "remote" in location.lower()
