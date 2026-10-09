"""
Agent 2: Job Discovery Agent
Discovers and normalizes jobs from LinkedIn search results.
"""

import logging
import re
from typing import Optional
from bs4 import BeautifulSoup

from ai_agent import Job

log = logging.getLogger(__name__)


class JobDiscoveryAgent:
    """Discovers and normalizes jobs from LinkedIn search results."""

    def __init__(self, browser, wait) -> None:
        self.browser = browser
        self.wait = wait

    def discover(self, position: str, location: str, max_pages: int = 3) -> list[Job]:
        """Discover jobs across multiple search pages."""
        all_jobs = []
        seen_ids = set()

        for page in range(max_pages):
            start = page * 25
            url = (
                f"https://www.linkedin.com/jobs/search/?f_LF=f_AL&keywords="
                f"{position}&location={location}&start={start}"
            )
            log.info(f"Discovering jobs page {page + 1}: {url}")
            self.browser.get(url)
            import time
            time.sleep(2)

            jobs = self._extract_from_page()
            new_jobs = [j for j in jobs if j.job_id not in seen_ids]
            all_jobs.extend(new_jobs)
            seen_ids.update(j.job_id for j in new_jobs)

            if len(new_jobs) < 10:
                break  # No more results

        log.info(f"Discovered {len(all_jobs)} total jobs")
        return all_jobs

    def _extract_from_page(self) -> list[Job]:
        """Extract jobs from current LinkedIn search page."""
        jobs = []
        try:
            page_source = self.browser.page_source
            soup = BeautifulSoup(page_source, "lxml")
            cards = soup.select('div[data-job-id]')

            for card in cards:
                job_id = card.get("data-job-id")
                if not job_id or job_id == "search":
                    continue

                title_el = card.select_one("h3.job-search-results__job-title")
                title = title_el.get_text(strip=True) if title_el else ""

                company_el = card.select_one("h4.job-search-results__company-name")
                company = company_el.get_text(strip=True) if company_el else ""

                loc_el = card.select_one("span.job-search-results__location")
                loc = loc_el.get_text(strip=True) if loc_el else ""

                date_el = card.select_one("span.job-search-results__posted-date")
                posted = date_el.get_text(strip=True) if date_el else ""

                jobs.append(Job(
                    job_id=job_id,
                    title=title,
                    company=company,
                    location=loc,
                    description=posted,
                ))
        except Exception as e:
            log.error(f"Error extracting jobs: {e}")

        return jobs

    def get_job_description(self, job_id: str) -> str:
        """Navigate to a job page and extract the full description."""
        url = f"https://www.linkedin.com/jobs/view/{job_id}"
        self.browser.get(url)
        import time
        time.sleep(2)

        try:
            content = self.browser.find_element(
                "css selector", ".jobs-description__content"
            )
            return content.text
        except Exception as e:
            log.error(f"Failed to get description for {job_id}: {e}")
            return ""

    def discover_with_descriptions(self, position: str, location: str,
                                    max_pages: int = 3) -> list[Job]:
        """Discover jobs and fetch full descriptions."""
        jobs = self.discover(position, location, max_pages)
        for job in jobs:
            job.description = self.get_job_description(job.job_id)
        return jobs