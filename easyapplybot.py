from __future__ import annotations

import shutil

import json
import csv
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta
import getpass
from pathlib import Path

import pandas as pd
import pyautogui
import yaml
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from selenium.webdriver.chrome.service import Service as ChromeService
import webdriver_manager.chrome as ChromeDriverManager
ChromeDriverManager = ChromeDriverManager.ChromeDriverManager
from company_filler import CompanyFiller
from ai_agent import AIAgent, AgentConfig
from agents.profile_agent import ProfileAgent
from agents.job_discovery import JobDiscoveryAgent
from agents.job_matching import JobMatchingAgent
from agents.resume_intelligence import ResumeIntelligenceAgent
from agents.application import ApplicationAgent
from agents.question import QuestionAgent
from agents.approval import ApprovalAgent
from agents.tracking import TrackingAgent
from agents.learning import LearningAgent
from agents.job_database import JobDatabase


log = logging.getLogger(__name__)


def first_visible_element(browser, by, selector):
    """Return the first displayed+enabled element matching the selector.

    LinkedIn renders duplicate form fields (a hidden placeholder plus the real
    input), so a bare find_element can grab the hidden one and fail to type.
    """
    for element in browser.find_elements(by, selector):
        if element.is_displayed() and element.is_enabled():
            return element
    return None


def setupLogger() -> None:
    dt: str = datetime.strftime(datetime.now(), "%m_%d_%y %H_%M_%S ")

    if not os.path.isdir('./logs'):
        os.mkdir('./logs')

    # TODO need to check if there is a log dir available or not
    logging.basicConfig(filename=('./logs/' + str(dt) + 'applyJobs.log'), filemode='w',
                        format='%(asctime)s::%(name)s::%(levelname)s::%(message)s', datefmt='./logs/%d-%b-%y %H:%M:%S')
    log.setLevel(logging.DEBUG)
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.DEBUG)
    c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
    c_handler.setFormatter(c_format)
    log.addHandler(c_handler)


class EasyApplyBot:
    setupLogger()
    # MAX_SEARCH_TIME is 10 hours by default, feel free to modify it
    MAX_SEARCH_TIME = 60 * 60

    def __init__(self,
                 username,
                 password,
                 phone_number,
                 # profile_path,
                 salary,
                 rate,
                 uploads={},
                 filename='output.csv',
                 blacklist=[],
                 blackListTitles=[],
                 experience_level=[],
                 name=None,
                 email=None,
                 parameters=None,
                 ) -> None:

        log.info("Welcome to Easy Apply Bot")
        dirpath: str = os.getcwd()
        log.info("current directory is : " + dirpath)
        log.info("Please wait while we prepare the bot for you")
        if experience_level:
            experience_levels = {
                1: "Entry level",
                2: "Associate",
                3: "Mid-Senior level",
                4: "Director",
                5: "Executive",
                6: "Internship"
            }
            applied_levels = [experience_levels[level] for level in experience_level]
            log.info("Applying for experience level roles: " + ", ".join(applied_levels))
        else:
            log.info("Applying for all experience levels")

        self.uploads = uploads
        self.salary = salary
        self.rate = rate
        # self.profile_path = profile_path
        past_ids: list | None = self.get_appliedIDs(filename)
        self.appliedJobIDs: list = past_ids if past_ids != None else []
        self.filename: str = filename
        self.options = self.browser_options()

        # Resolve chromedriver: PATH → bundled assets/ → webdriver_manager auto-fetch
        # The bundled assets are architecture-specific and may not match this machine
        # (e.g. x86_64 driver on arm64), so validate before use and fall back to
        # webdriver_manager, which fetches a driver matching this Chrome + architecture.
        import platform
        import subprocess

        def _driver_executable(path: str) -> bool:
            """Return True if the driver binary actually runs on this machine."""
            if not path or not os.path.exists(path):
                return False
            try:
                subprocess.run([path, "--version"], capture_output=True, timeout=10, check=True)
                return True
            except Exception:
                return False

        chromedriver_path = shutil.which("chromedriver")
        if not chromedriver_path:
            # Fallback to local assets directory
            system = platform.system().lower()
            if system == "darwin":
                local_path = os.path.join(os.path.dirname(__file__), "assets", "chromedriver_darwin")
            elif system == "windows":
                local_path = os.path.join(os.path.dirname(__file__), "assets", "chromedriver_windows")
            else:
                local_path = os.path.join(os.path.dirname(__file__), "assets", "chromedriver_linux")
            if os.path.exists(local_path):
                os.chmod(local_path, 0o755)
                if _driver_executable(local_path):
                    chromedriver_path = local_path

        if not chromedriver_path:
            # Last resort: let webdriver_manager fetch a driver matching this Chrome + arch
            chromedriver_path = ChromeDriverManager().install()

        chrome_path = shutil.which("chromium") or shutil.which("google-chrome")
        if not chrome_path:
            # Fallback to common macOS Chrome paths
            chrome_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ]
            for cp in chrome_paths:
                if os.path.exists(cp):
                    chrome_path = cp
                    break

        if not chromedriver_path:
            raise FileNotFoundError("Chromedriver not found in PATH or assets/ directory.")
        if not chrome_path:
            raise FileNotFoundError("Chromium/Chrome not found in PATH or common locations.")

        self.options.binary_location = chrome_path
        self.browser = webdriver.Chrome(service=ChromeService(chromedriver_path), options=self.options)

        self.wait = WebDriverWait(self.browser, 30)
        self.blacklist = blacklist
        self.blackListTitles = blackListTitles
        self.start_linkedin(username, password)
        self.phone_number = phone_number
        self.experience_level = experience_level
        # Personal info for company career page forms
        self.personal_info = {'name': name or '', 'email': email or '', 'phone': phone_number or ''}
        # Company career page filler
        self.company_filler = CompanyFiller(self.browser, self.wait, self.personal_info, uploads)

        # AI configuration shared by the agents below
        ai_config = (parameters or {}).get('ai', {})
        self.ai_config = ai_config

        # Agent 1: Profile Agent
        self.profile_agent = ProfileAgent(config=parameters or {})

        # Agent 2: Job Discovery Agent
        self.job_discovery_agent = JobDiscoveryAgent(self.browser, self.wait)

        # Agent 3: Job Matching Agent
        self.job_matching_agent = JobMatchingAgent(AgentConfig(
            provider=self.ai_config.get('provider', 'both'),
            model=self.ai_config.get('model', 'gpt-4o'),
            anthropic_model=self.ai_config.get('anthropic_model', 'claude-sonnet-4'),
            threshold=self.ai_config.get('scoring_threshold', 0.7),
            max_jobs=self.ai_config.get('max_jobs_per_run', 20),
            batch_size=self.ai_config.get('batch_size', 10),
            human_approval=self.ai_config.get('human_approval', False),
            review_file=self.ai_config.get('review_file', 'review_batch.md'),
            timeout_minutes=self.ai_config.get('api_timeout_minutes', 10),
            recency_priority=self.ai_config.get('recency_priority', True),
        ))

        # Agent 4: Resume Intelligence Agent
        resume_path = (parameters or {}).get('resume_sample', '')
        self.resume_agent = ResumeIntelligenceAgent(resume_path)

        # Agent 5: Application Agent
        self.application_agent = ApplicationAgent(
            self.browser, self.wait, self.company_filler)

        # Agent 6: Question Agent
        self.question_agent = QuestionAgent('qa.csv')

        # Agent 7: Approval Agent
        self.approval_agent = ApprovalAgent(
            review_file=self.ai_config.get('review_file', 'review_batch.md'),
            human_approval=self.ai_config.get('human_approval', False),
            timeout_minutes=self.ai_config.get('api_timeout_minutes', 10),
        )

        # Agent 8: Tracking Agent
        self.tracking_agent = TrackingAgent(filename)

        # Agent 9: Learning Agent
        self.learning_agent = LearningAgent('learning.json', filename)

        # Job Database Agent — canonical job store
        self.job_database = JobDatabase('jobs.db')

        # AI Agent (kept for backward compatibility)
        self.ai_agent = AIAgent(
            AgentConfig(
                provider=self.ai_config.get('provider', 'both'),
                model=self.ai_config.get('model', 'gpt-4o'),
                anthropic_model=self.ai_config.get('anthropic_model', 'claude-sonnet-4'),
                threshold=self.ai_config.get('scoring_threshold', 0.7),
                max_jobs=self.ai_config.get('max_jobs_per_run', 20),
                batch_size=self.ai_config.get('batch_size', 10),
                human_approval=self.ai_config.get('human_approval', False),
                review_file=self.ai_config.get('review_file', 'review_batch.md'),
                timeout_minutes=self.ai_config.get('api_timeout_minutes', 10),
                recency_priority=self.ai_config.get('recency_priority', True),
            ),
            resume_text=(parameters or {}).get('resume_sample', ''),
        )

        # -------------------------

        self.locator = {
            "next": (By.CSS_SELECTOR, "button[aria-label='Continue to next step']"),
            "review": (By.CSS_SELECTOR, "button[aria-label='Review your application']"),
            "submit": (By.CSS_SELECTOR, "button[aria-label='Submit application']"),
            "error": (By.CLASS_NAME, "artdeco-inline-feedback__message"),
            "upload_resume": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]"),
            "upload_cv": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]"),
            "follow": (By.CSS_SELECTOR, "label[for='follow-company-checkbox']"),
            "upload": (By.NAME, "file"),
            "search": (By.CSS_SELECTOR, "ul.jobs-search-results-list, ul.base-search-card, div.jobs-search-results-list"),
            "links": (By.CSS_SELECTOR, "div.job-search-card"),
            "fields": (By.CLASS_NAME, "jobs-easy-apply-form-section__grouping"),
            "radio_select": (By.CSS_SELECTOR, "input[type='radio']"), #need to append [value={}].format(answer)
            "multi_select": (By.XPATH, "//*[contains(@id, 'text-entity-list-form-component')]"),
            "text_select": (By.CLASS_NAME, "artdeco-text-input--input"),
            "2fa_oneClick": (By.ID, 'reset-password-submit-button'),
            "easy_apply_button": (By.XPATH, '//button[contains(@class, "jobs-apply-button")]')

        }

        #initialize questions and answers file
        self.qa_file = Path("qa.csv")
        self.answers = {}

        #if qa file exists, load it
        if self.qa_file.is_file():
            df = pd.read_csv(self.qa_file)
            for index, row in df.iterrows():
                self.answers[row['Question']] = row['Answer']
        #if qa file does not exist, create it
        else:
            df = pd.DataFrame(columns=["Question", "Answer"])
            df.to_csv(self.qa_file, index=False, encoding='utf-8')


    def get_appliedIDs(self, filename) -> list | None:
        try:
            df = pd.read_csv(filename,
                             header=None,
                             names=['timestamp', 'jobID', 'job', 'company', 'attempted', 'result'],
                             lineterminator='\n',
                             encoding='utf-8')

            df['timestamp'] = pd.to_datetime(df['timestamp'], format="%Y-%m-%d %H:%M:%S")
            df = df[df['timestamp'] > (datetime.now() - timedelta(days=2))]
            jobIDs: list = list(df.jobID)
            log.info(f"{len(jobIDs)} jobIDs found")
            return jobIDs
        except Exception as e:
            log.info(str(e) + "   jobIDs could not be loaded from CSV {}".format(filename))
            return None

    def browser_options(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument('--no-sandbox')
        options.add_argument("--disable-extensions")
        #options.add_argument(r'--remote-debugging-port=9222')
        #options.add_argument(r'--profile-directory=Person 1')

        # Disable webdriver flags or you will be easily detectable
        options.add_argument("--disable-blink-features")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Load user profile
        #options.add_argument(r"--user-data-dir={}".format(self.profile_path))
        return options

    def start_linkedin(self, username, password) -> None:
        log.info("Logging in.....Please wait :)  ")
        self.browser.get("https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin")
        try:
            # LinkedIn randomizes element IDs and renders duplicate hidden+visible
            # form fields, so locate by input type and the Sign in button's text,
            # preferring the visible element.  Retry a few times in case the page
            # is still rendering (the fields are often hidden until load completes).
            user_field = pw_field = login_button = None
            for attempt in range(5):
                time.sleep(2)
                user_field = first_visible_element(self.browser, By.CSS_SELECTOR, 'input[type="email"]')
                pw_field = first_visible_element(self.browser, By.CSS_SELECTOR, 'input[type="password"]')
                login_button = first_visible_element(
                    self.browser, By.XPATH, '//button[normalize-space()="Sign in"]'
                )
                if user_field and pw_field and login_button:
                    break
                log.debug(f"Login fields not ready yet (attempt {attempt+1}/5), retrying...")

            if not user_field or not pw_field:
                raise TimeoutException("Login fields not found after retries")

            user_field.send_keys(username)
            user_field.send_keys(Keys.TAB)
            time.sleep(2)
            pw_field.send_keys(password)
            time.sleep(2)
            # Re-locate the button to avoid stale element after page mutations
            login_button = first_visible_element(
                self.browser, By.XPATH, '//button[normalize-space()="Sign in"]'
            )
            if login_button:
                login_button.click()
            time.sleep(15)
            # if self.is_present(self.locator["2fa_oneClick"]):
            #     oneclick_auth = self.browser.find_element(by='id', value='reset-password-submit-button')
            #     if oneclick_auth is not None:
            #         log.info("additional authentication required, sleep for 15 seconds so you can do that")
            #         time.sleep(15)
            # else:
            #     time.sleep()
        except (TimeoutException, NoSuchElementException):
            log.info("TimeoutException! Username/password field or login button not found")

    def fill_data(self) -> None:
        # Window manipulation removed — was causing browser offscreen.
        pass

    def start_apply(self, positions, locations) -> None:
        start: float = time.time()
        self.fill_data()
        self.positions = positions
        self.locations = locations
        combos: list = []
        while len(combos) < len(positions) * len(locations):
            position = positions[random.randint(0, len(positions) - 1)]
            location = locations[random.randint(0, len(locations) - 1)]
            combo: tuple = (position, location)
            if combo not in combos:
                combos.append(combo)
                log.info(f"Applying to {position}: {location}")
                location = "&location=" + location
                self.applications_loop(position, location)
            if len(combos) > 500:
                break

    # self.finish_apply() --> this does seem to cause more harm than good, since it closes the browser which we usually don't want, other conditions will stop the loop and just break out

    def applications_loop(self, position, location):
        """AI-driven application loop — agentic flow."""
        start_time: float = time.time()
        jobs_per_page = 0
        all_jobs: list = []

        log.info("Looking for jobs.. Please wait..")

        try:
            self.browser.set_window_position(1, 1)
        except Exception:
            # Chrome refuses to move a maximized window; ignore and continue.
            pass
        self.browser.maximize_window()
        self.browser, _ = self.next_jobs_page(position, location, jobs_per_page, experience_level=self.experience_level)
        log.info("Looking for jobs.. Please wait..")

        while time.time() - start_time < self.MAX_SEARCH_TIME:
            try:
                log.info(f"{(self.MAX_SEARCH_TIME - (time.time() - start_time)) // 60} minutes left in this search")

                randoTime: float = random.uniform(1.5, 2.9)
                log.debug(f"Sleeping for {round(randoTime, 1)}")
                self.load_page(sleep=0.5)

                # Scroll the results pane to lazy-load more job cards.
                # LinkedIn no longer uses a stable container class, so scroll any
                # scrollable element on the page.
                self.browser.execute_script("""
                    const els = document.querySelectorAll('*');
                    for (const el of els) {
                        const cs = window.getComputedStyle(el);
                        if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll')
                            && el.scrollHeight > el.clientHeight + 100) {
                            el.scrollTo(0, el.scrollHeight);
                            return true;
                        }
                    }
                    window.scrollTo(0, document.body.scrollHeight);
                    return false;
                """)
                time.sleep(1)

                links = self.get_elements("links")
                log.info(f"DEBUG: found {len(links)} job cards on this page (URL: {self.browser.current_url[:80]})")
                if not links:
                    # LinkedIn sometimes redirects to a "currentJobId" page after an
                    # application; re-navigate to the clean search URL and retry.
                    log.warning("No job cards found – re-navigating to search URL")
                    self.browser, _ = self.next_jobs_page(position, location, jobs_per_page, experience_level=self.experience_level)
                    time.sleep(2)
                    links = self.get_elements("links")
                    log.info(f"DEBUG: after re-nav, found {len(links)} job cards")
                if links:
                    log.info(f"Found {len(links)} job cards on this page")

                    # Process ONE job at a time: extract → score → customize → submit → next
                    for link in links:
                        if 'Applied' in link.text:
                            continue
                        if link.text in self.blacklist:
                            continue

                        jobID = link.get_attribute("data-job-id") or self._extract_job_id(link)
                        if not jobID or jobID == "search":
                            log.debug("Job ID not found, search keyword found instead? {}".format(link.text))
                            continue
                        if jobID in self.appliedJobIDs:
                            log.info(f"Job {jobID} already applied, skipping")
                            continue

                        log.info(f"Processing job {jobID}: {link.text.splitlines()[0] if link.text else ''}")
                        # Apply to this single job before moving to the next
                        self._ai_apply_batch({jobID: "To be processed"})
                        self.appliedJobIDs.append(jobID)

                    jobs_per_page += 25
                    self.browser, _ = self.next_jobs_page(position,
                                                          location,
                                                          jobs_per_page,
                                                          experience_level=self.experience_level)
            except Exception as e:
                print(e)

    def _ai_apply_batch(self, jobIDs: dict):
        """Agentic batch: extract, store, score, customize, decide, submit."""
        from ai_agent import Job

        # 1. Extract jobs and store in canonical database
        jobs_to_process = []
        for jobID, status in jobIDs.items():
            if status != "To be processed":
                continue
            self.get_job_page(jobID)
            time.sleep(1)

            # Extract description from page
            description = ""
            try:
                description = self.browser.find_element(By.CSS_SELECTOR, ".jobs-description__content").text
            except Exception:
                pass

            title = self.browser.title.split(' | ')[0] if ' | ' in self.browser.title else self.browser.title
            company = self.browser.title.split(' | ')[1] if ' | ' in self.browser.title else ""
            url = self.browser.current_url

            # Add to job database
            self.job_database.add_job(
                job_id=jobID,
                company=company,
                title=title,
                location="",  # LinkedIn doesn't always show location on job page
                description=description,
                source="linkedin",
                url=url,
                decision="pending"
            )
            jobs_to_process.append(jobID)

        if not jobs_to_process:
            return

        # 2. Fetch all pending jobs from database (in case we have carryover)
        pending_jobs_dicts = self.job_database.get_pending_jobs(limit=100)  # reasonable limit
        if not pending_jobs_dicts:
            return

        # Convert dicts to Job objects for scoring
        jobs = []
        for job_dict in pending_jobs_dicts:
            jobs.append(Job(
                job_id=job_dict["job_id"],
                title=job_dict["title"],
                company=job_dict["company"],
                location=job_dict["location"],
                description=job_dict["description"],
            ))

        # 3. AI scoring and filtering
        scored = self.job_matching_agent.match(
            jobs, self.profile_agent.get(), provider=self.ai_config.get('provider', 'anthropic')
        )  # JobMatchingAgent.match expects profile dict
        if not scored:
            log.info("No jobs passed matching threshold")
            return

        # 4. Get top N for resume evaluation
        top_jobs = scored[:self.job_matching_agent.config.batch_size]

        # 5. Resume Intelligence evaluation (3 personas)
        for job in top_jobs:
            evaluations = self.resume_agent.evaluate(job, provider=self.ai_config.get('provider', 'anthropic'))
            # Store scores back to job database
            self.job_database.update_job(
                job.job_id,
                recruiter_score=evaluations["recruiter"],
                hiring_manager_score=evaluations["hiring_manager"],
                ats_score=evaluations["ats"],
                composite_score=evaluations["composite"],
                decision="evaluated"
            )
            # Also customize the actual resume text for application
            self.resume_agent.optimize(job, provider=self.ai_config.get('provider', 'anthropic'))

        # 6. Decision: auto-approve based on composite score
        approved_jobs = []
        for job in top_jobs:
            job_record = self.job_database.get_job(job.job_id)
            if job_record and job_record.get("composite_score", 0) >= 0.7:  # threshold
                self.job_database.update_job(
                    job.job_id,
                    decision="approved",
                    status="approved"
                )
                approved_jobs.append(job)
            else:
                self.job_database.update_job(
                    job.job_id,
                    decision="skipped",
                    status="skipped",
                    decision_reason="Low composite score"
                )

        # 7. Submit approved jobs
        for job in approved_jobs:
            log.info(f"Submitting approved job: {job.title} @ {job.company}")
            result = self.application_agent.apply(job, self.apply_to_job)
            if result:
                self.job_database.update_job(
                    job.job_id,
                    status="applied",
                    applied_timestamp=datetime.now().isoformat()
                )
                self.tracking_agent.track(
                    job.job_id, job.title, job.company, result, attempted=True
                )
                self.learning_agent.learn_from_outcomes()  # Update learning after each batch
            else:
                self.job_database.update_job(
                    job.job_id,
                    status="failed",
                    applied_timestamp=datetime.now().isoformat()
                )
                self.tracking_agent.track(
                    job.job_id, job.title, job.company, result, attempted=True
                )

    def apply_to_job(self, jobID):
        # get job page
        self.get_job_page(jobID)

        # let page load
        time.sleep(1)

        # get easy apply button
        button = self.get_easy_apply_button()

        # word filter to skip positions not wanted
        if button is not False:
            if any(word in self.browser.title for word in self.blackListTitles):
                log.info('skipping this application, a blacklisted keyword was found in the job position')
                string_easy = "* Contains blacklisted keyword"
                result = False
            else:
                string_easy = "* has Easy Apply Button"
                log.info("Clicking the EASY apply button")
                button.click()
                clicked = True
                time.sleep(1)
                self.fill_out_fields()
                result: bool = self.send_resume()
                if result:
                    string_easy = "*Applied: Sent Resume"
                else:
                    string_easy = "*Did not apply: Failed to send Resume"
        elif "You applied on" in self.browser.page_source:
            log.info("You have already applied to this position.")
            string_easy = "* Already Applied"
            result = False
        else:
            log.info("The Easy apply button does not exist.")
            string_easy = "* Doesn't have Easy Apply Button"
            # Try company career page
            result = self._apply_via_company_site()
            if result:
                string_easy = "* Applied via company site"
            else:
                string_easy = "* No apply path found"

        log.info(f"\nPosition {jobID}:\n {self.browser.title} \n {string_easy} \n")

        self.write_to_file(button, jobID, self.browser.title, result)
        return result

    def _apply_via_company_site(self) -> bool:
        """Look for 'Apply on company site' link and fill via CompanyFiller."""
        try:
            # Find external apply links on the job page
            links = self.browser.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href") or ""
                text = (link.text or "").lower()
                if any(kw in text for kw in ["apply on company site", "apply on", "external apply", "apply through"]) or \
                   any(kw in href.lower() for kw in ["greenhouse", "lever", "workday", "ashby", "jobvite", "icims", "smartrecruiters", "taleo"]):
                    log.info(f"Found company apply link: {href}")
                    return self.company_filler.fill_and_submit(href)
            log.info("No company apply link found")
            return False
        except Exception as e:
            log.error(f"Company site apply failed: {e}")
            return False

    def write_to_file(self, button, jobID, browserTitle, result) -> None:
        def re_extract(text, pattern):
            target = re.search(pattern, text)
            if target:
                target = target.group(1)
            return target

        timestamp: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        attempted: bool = False if button == False else True
        job = re_extract(browserTitle.split(' | ')[0], r"\(?\d?\)?\s?(\w.*)")
        company = re_extract(browserTitle.split(' | ')[1], r"(\w.*)")

        toWrite: list = [timestamp, jobID, job, company, attempted, result]
        with open(self.filename, 'a+') as f:
            writer = csv.writer(f)
            writer.writerow(toWrite)

    def get_job_page(self, jobID):

        job: str = 'https://www.linkedin.com/jobs/view/' + str(jobID)
        self.browser.get(job)
        self.job_page = self.load_page(sleep=0.5)
        return self.job_page

    def _extract_job_id(self, element):
        """Extract the numeric job ID from a LinkedIn job card.

        LinkedIn moved from a stable `data-job-id` attribute to a
        `data-entity-urn` like `urn:li:jobPosting:123456789`.  This helper
        falls back to parsing the anchor's href for the trailing numeric ID.
        """
        # Preferred: data-entity-urn="urn:li:jobPosting:123456789"
        urn = element.get_attribute("data-entity-urn")
        if urn:
            parts = urn.split(":")
            if len(parts) >= 3 and parts[-1].isdigit():
                return parts[-1]

        # Fallback: parse the link href
        try:
            a = element.find_element(By.TAG_NAME, "a")
            href = a.get_attribute("href") or ""
            import re
            m = re.search(r"/jobs/view/[^/]*-(\d+)", href)
            if m:
                return m.group(1)
        except Exception:
            pass

        return None

    def get_easy_apply_button(self):
        EasyApplyButton = False
        try:
            buttons = self.get_elements("easy_apply_button")
            # buttons = self.browser.find_elements("xpath",
            #     '//button[contains(@class, "jobs-apply-button")]'
            # )
            for button in buttons:
                if "Easy Apply" in button.text:
                    EasyApplyButton = button
                    self.wait.until(EC.element_to_be_clickable(EasyApplyButton))
                else:
                    log.debug("Easy Apply button not found")
            
        except Exception as e: 
            print("Exception:",e)
            log.debug("Easy Apply button not found")


        return EasyApplyButton

    def fill_out_fields(self):
        fields = self.browser.find_elements(By.CLASS_NAME, "jobs-easy-apply-form-section__grouping")
        for field in fields:

            if "Mobile phone number" in field.text:
                field_input = field.find_element(By.TAG_NAME, "input")
                field_input.clear()
                field_input.send_keys(self.phone_number)


        return


    def get_elements(self, type) -> list:
        elements = []
        element = self.locator[type]
        if self.is_present(element):
            elements = self.browser.find_elements(element[0], element[1])
        return elements

    def is_present(self, locator):
        return len(self.browser.find_elements(locator[0],
                                              locator[1])) > 0

    def send_resume(self) -> bool:
        def is_present(button_locator) -> bool:
            return len(self.browser.find_elements(button_locator[0],
                                                  button_locator[1])) > 0

        try:
            #time.sleep(random.uniform(1.5, 2.5))
            next_locator = (By.CSS_SELECTOR,
                            "button[aria-label='Continue to next step']")
            review_locator = (By.CSS_SELECTOR,
                              "button[aria-label='Review your application']")
            submit_locator = (By.CSS_SELECTOR,
                              "button[aria-label='Submit application']")
            error_locator = (By.CLASS_NAME,"artdeco-inline-feedback__message")
            upload_resume_locator = (By.XPATH, '//span[text()="Upload resume"]')
            upload_cv_locator = (By.XPATH, '//span[text()="Upload cover letter"]')
            # WebElement upload_locator = self.browser.find_element(By.NAME, "file")
            follow_locator = (By.CSS_SELECTOR, "label[for='follow-company-checkbox']")

            submitted = False
            loop = 0
            while loop < 2:
                time.sleep(1)
                # Upload resume
                if is_present(upload_resume_locator):
                    #upload_locator = self.browser.find_element(By.NAME, "file")
                    try:
                        resume_locator = self.browser.find_element(By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]")
                        resume = self.uploads["Resume"]
                        resume_locator.send_keys(resume)
                    except Exception as e:
                        log.error(e)
                        log.error("Resume upload failed")
                        log.debug("Resume: " + resume)
                        log.debug("Resume Locator: " + str(resume_locator))
                # Upload cover letter if possible
                if is_present(upload_cv_locator):
                    cv = self.uploads["Cover Letter"]
                    cv_locator = self.browser.find_element(By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]")
                    cv_locator.send_keys(cv)

                    #time.sleep(random.uniform(4.5, 6.5))
                elif len(self.get_elements("follow")) > 0:
                    elements = self.get_elements("follow")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()

                if len(self.get_elements("submit")) > 0:
                    elements = self.get_elements("submit")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()
                        log.info("Application Submitted")
                        submitted = True
                        break

                elif len(self.get_elements("error")) > 0:
                    elements = self.get_elements("error")
                    if "application was sent" in self.browser.page_source:
                        log.info("Application Submitted")
                        submitted = True
                        break
                    elif len(elements) > 0:
                        while len(elements) > 0:
                            log.info("Please answer the questions, waiting 5 seconds...")
                            time.sleep(5)
                            elements = self.get_elements("error")

                            for element in elements:
                                self.process_questions()

                            if "application was sent" in self.browser.page_source:
                                log.info("Application Submitted")
                                submitted = True
                                break
                            elif is_present(self.locator["easy_apply_button"]):
                                log.info("Skipping application")
                                submitted = False
                                break
                        continue
                        #add explicit wait
                    
                    else:
                        log.info("Application not submitted")
                        time.sleep(2)
                        break
                    # self.process_questions()

                elif len(self.get_elements("next")) > 0:
                    elements = self.get_elements("next")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()

                elif len(self.get_elements("review")) > 0:
                    elements = self.get_elements("review")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()

                elif len(self.get_elements("follow")) > 0:
                    elements = self.get_elements("follow")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()

        except Exception as e:
            log.error(e)
            log.error("cannot apply to this job")
            pass
            #raise (e)

        return submitted
    def process_questions(self):
        time.sleep(1)
        form = self.get_elements("fields") #self.browser.find_elements(By.CLASS_NAME, "jobs-easy-apply-form-section__grouping")
        for field in form:
            question = field.text
            answer = self.ans_question(question.lower())
            #radio button
            if self.is_present(self.locator["radio_select"]):
                try:
                    input = field.find_element(By.CSS_SELECTOR, "input[type='radio'][value={}]".format(answer))
                    input.execute_script("arguments[0].click();", input)
                except Exception as e:
                    log.error(e)
                    continue
            #multi select
            elif self.is_present(self.locator["multi_select"]):
                try:
                    input = field.find_element(self.locator["multi_select"])
                    input.send_keys(answer)
                except Exception as e:
                    log.error(e)
                    continue
            # text box
            elif self.is_present(self.locator["text_select"]):
                try:
                    input = field.find_element(self.locator["text_select"])
                    input.send_keys(answer)
                except Exception as e:
                    log.error(e)
                    continue

            elif self.is_present(self.locator["text_select"]):
               pass

            if answer in ("Yes", "No"): #radio button
                try: #debug this
                    input = form.find_element(By.CSS_SELECTOR, "input[type='radio'][value={}]".format(answer))
                    form.execute_script("arguments[0].click();", input)
                except:
                    pass


            else:
                input = form.find_element(By.CLASS_NAME, "artdeco-text-input--input")
                input.send_keys(answer)

    def ans_question(self, question): #refactor this to an ans.yaml file
        answer = None
        if "how many" in question:
            answer = "1"
        elif "experience" in question:
            answer = "1"
        elif "sponsor" in question:
            answer = "No"
        elif 'do you ' in question:
            answer = "Yes"
        elif "have you " in question:
            answer = "Yes"
        elif "US citizen" in question:
            answer = "Yes"
        elif "are you " in question:
            answer = "Yes"
        elif "salary" in question:
            answer = self.salary
        elif "can you" in question:
            answer = "Yes"
        elif "gender" in question:
            answer = "Male"
        elif "race" in question:
            answer = "Wish not to answer"
        elif "lgbtq" in question:
            answer = "Wish not to answer"
        elif "ethnicity" in question:
            answer = "Wish not to answer"
        elif "nationality" in question:
            answer = "Wish not to answer"
        elif "government" in question:
            answer = "I do not wish to self-identify"
        elif "are you legally" in question:
            answer = "Yes"
        else:
            log.info("Not able to answer question automatically. Please provide answer")
            #open file and document unanswerable questions, appending to it
            answer = "user provided"
            try:
                user_input = input(f"Answer for '{question}': ").strip()
                if user_input:
                    answer = user_input
            except (EOFError, KeyboardInterrupt):
                log.warning("No interactive input available, skipping question.")

            # df = pd.DataFrame(self.answers, index=[0])
            # df.to_csv(self.qa_file, encoding="utf-8")
        log.info("Answering question: " + question + " with answer: " + answer)

        # Append question and answer to the CSV
        if question not in self.answers:
            self.answers[question] = answer
            # Append a new question-answer pair to the CSV file
            new_data = pd.DataFrame({"Question": [question], "Answer": [answer]})
            new_data.to_csv(self.qa_file, mode='a', header=False, index=False, encoding='utf-8')
            log.info(f"Appended to QA file: '{question}' with answer: '{answer}'.")

        return answer

    def load_page(self, sleep=1):
        scroll_page = 0
        while scroll_page < 4000:
            self.browser.execute_script("window.scrollTo(0," + str(scroll_page) + " );")
            scroll_page += 500
            time.sleep(sleep)

        if sleep != 1:
            self.browser.execute_script("window.scrollTo(0,0);")
            time.sleep(sleep)

        page = BeautifulSoup(self.browser.page_source, "lxml")
        return page

    def avoid_lock(self) -> None:
        x, _ = pyautogui.position()
        pyautogui.moveTo(x + 200, pyautogui.position().y, duration=1.0)
        pyautogui.moveTo(x, pyautogui.position().y, duration=0.5)
        pyautogui.keyDown('ctrl')
        pyautogui.press('esc')
        pyautogui.keyUp('ctrl')
        time.sleep(0.5)
        pyautogui.press('esc')

    def next_jobs_page(self, position, location, jobs_per_page, experience_level=[]):
        # Construct the experience level part of the URL
        experience_level_str = ",".join(map(str, experience_level)) if experience_level else ""
        experience_level_param = f"&f_E={experience_level_str}" if experience_level_str else ""
        # Build a clean search URL – LinkedIn sometimes redirects to a
        # "currentJobId" page after an application, which has no job cards.
        url = ("https://www.linkedin.com/jobs/search/?keywords=" +
               position + location + "&start=" + str(jobs_per_page) +
               experience_level_param)
        self.browser.get(url)
        log.info("Loading next job page?")

        # Wait for job cards to actually load (LinkedIn is slow to render them)
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        try:
            WebDriverWait(self.browser, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.job-search-card"))
            )
            log.info(f"Job cards loaded on page (start={jobs_per_page})")
        except Exception:
            log.warning("Timed out waiting for job cards to load")
        self.load_page()
        return (self.browser, jobs_per_page)

    # def finish_apply(self) -> None:
    #     self.browser.close()


if __name__ == '__main__':

    with open("config.yaml", 'r') as stream:
        try:
            parameters = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise exc

    assert len(parameters['positions']) > 0
    assert len(parameters['locations']) > 0
    assert parameters['username'] is not None
    assert parameters['password'] is not None
    assert parameters['phone_number'] is not None


    if 'uploads' in parameters.keys() and type(parameters['uploads']) == list:
        raise Exception("uploads read from the config file appear to be in list format" +
                        " while should be dict. Try removing '-' from line containing" +
                        " filename & path")

    log.info({k: parameters[k] for k in parameters.keys() if k not in ['username', 'password']})

    output_filename: list = [f for f in parameters.get('output_filename', ['output.csv']) if f is not None]
    output_filename: list = output_filename[0] if len(output_filename) > 0 else 'output.csv'
    blacklist = parameters.get('blacklist', [])
    blackListTitles = parameters.get('blackListTitles', [])

    uploads = {} if parameters.get('uploads', {}) is None else parameters.get('uploads', {})
    for key in uploads.keys():
        assert uploads[key] is not None

    # Personal info for company career page forms
    personal_info = {
        'name': parameters.get('name', ''),
        'email': parameters.get('email', ''),
        'phone': parameters.get('phone_number', ''),
    }

    locations: list = [l for l in parameters['locations'] if l is not None]
    positions: list = [p for p in parameters['positions'] if p is not None]

    bot = EasyApplyBot(parameters['username'],
                       parameters['password'],
                       parameters['phone_number'],
                       parameters['salary'],
                       parameters['rate'],
                       uploads=uploads,
                       filename=output_filename,
                       blacklist=blacklist,
                       blackListTitles=blackListTitles,
                       experience_level=parameters.get('experience_level', []),
                       name=parameters.get('name'),
                       email=parameters.get('email'),
                       parameters=parameters
                       )
    bot.start_apply(positions, locations)


