"""
Agent 5: Application Agent
Navigates and fills applications on LinkedIn and company career sites.
"""

import logging
from typing import Optional

from company_filler import CompanyFiller

log = logging.getLogger(__name__)


class ApplicationAgent:
    """Navigates and fills applications."""

    def __init__(self, browser, wait, company_filler: CompanyFiller) -> None:
        self.browser = browser
        self.wait = wait
        self.company_filler = company_filler

    def apply(self, job, easy_apply_func) -> bool:
        """Apply to a job using Easy Apply or company site."""
        # Try Easy Apply first
        result = easy_apply_func(job.job_id)
        if result:
            return True

        # Fall back to company career page
        return self._apply_via_company_site(job)

    def _apply_via_company_site(self, job) -> bool:
        """Find and fill company career page."""
        try:
            links = self.browser.find_elements("tag name", "a")
            for link in links:
                href = link.get_attribute("href") or ""
                text = (link.text or "").lower()
                if any(kw in text for kw in [
                    "apply on company site", "apply on",
                    "external apply", "apply through"
                ]) or any(kw in href.lower() for kw in [
                    "greenhouse", "lever", "workday", "ashby",
                    "jobvite", "icims", "smartrecruiters", "taleo"
                ]):
                    log.info(f"Found company apply link: {href}")
                    return self.company_filler.fill_and_submit(href)
            log.info("No company apply link found")
            return False
        except Exception as e:
            log.error(f"Company site apply failed: {e}")
            return False