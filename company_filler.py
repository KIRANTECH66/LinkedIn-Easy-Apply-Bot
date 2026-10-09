"""
ATS-specific form fillers for company career pages.

Detects the ATS from the URL and fills known form patterns.
Falls back gracefully on unrecognized sites.
"""

import logging
import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

log = logging.getLogger(__name__)


class CompanyFiller:
    """Fill and submit application forms on company career pages."""

    # ATS URL fingerprints
    ATS_SIGNATURES = {
        "greenhouse": ["greenhouse.jobs", "/greenhouse/"],
        "lever": ["/lever/"],
        "workday": ["/workday/"],
        "ashby": ["/ashby/"],
        "jobvite": ["/jobvite/"],
        "icims": ["/icims/"],
        "smartrecruiters": ["/smartrecruiters/"],
        "taleo": ["/taleo/"],
    }

    def __init__(self, browser, wait, config: dict, uploads: dict = None) -> None:
        self.browser = browser
        self.wait = wait
        self.config = config
        self.uploads = uploads or {}
        self.filled_fields: list[str] = []

    def detect_ats(self, url: str) -> Optional[str]:
        """Return ATS name if URL matches a known signature, else None."""
        url_lower = url.lower()
        for ats, signatures in self.ATS_SIGNATURES.items():
            if any(sig in url_lower for sig in signatures):
                return ats
        return None

    def fill_and_submit(self, url: str) -> bool:
        """Navigate to url, fill the form, attempt submit. Returns True if submitted."""
        log.info(f"Navigating to company site: {url}")
        self.browser.get(url)
        time.sleep(2)

        ats = self.detect_ats(url)
        if ats is None:
            log.warning("Unrecognized ATS — attempting generic fill")
            return self._fill_generic()

        log.info(f"Detected ATS: {ats}")
        filler = getattr(self, f"_fill_{ats}", self._fill_generic)
        try:
            result = filler()
        except Exception as e:
            log.error(f"Error filling {ats} form: {e}")
            return False

        if result:
            self._take_screenshot("company_applied")
        return result

    # ─── Greenhouse ───────────────────────────────────────────────

    def _fill_greenhouse(self) -> bool:
        filled = False
        # Name
        filled |= self._fill_input('input[name="candidate[name]"]', self.config.get("name", ""))
        # Email
        filled |= self._fill_input('input[name="candidate[email]"]', self.config.get("email", ""))
        # Phone
        filled |= self._fill_input('input[name="candidate[phone]"]', self.config.get("phone", ""))
        # Resume upload
        filled |= self._upload_file('input[type="file"][accept*="pdf"]', "Resume")
        # Cover letter upload
        filled |= self._upload_file('input[type="file"][accept*="pdf"]', "Cover Letter", multiple=True)
        # Text questions
        filled |= self._fill_textareas()

        if filled:
            self._click_submit()
        return filled

    # ─── Lever ────────────────────────────────────────────────────

    def _fill_lever(self) -> bool:
        filled = False
        filled |= self._fill_input('input[name="name"]', self.config.get("name", ""))
        filled |= self._fill_input('input[name="email"]', self.config.get("email", ""))
        filled |= self._fill_input('textarea[name="phone"]', self.config.get("phone", ""))
        filled |= self._upload_file('input[type="file"]', "Resume")
        filled |= self._fill_textareas()

        if filled:
            self._click_submit()
        return filled

    # ─── Workday ──────────────────────────────────────────────────

    def _fill_workday(self) -> bool:
        # Workday forms are multi-page and highly variable.
        # Best-effort: fill any visible text inputs with matching labels.
        log.info("Workday detected — attempting best-effort fill")
        filled = self._fill_by_label()
        if filled:
            self._click_submit()
        return filled

    # ─── Generic fallback ─────────────────────────────────────────

    def _fill_generic(self) -> bool:
        """Try to fill any visible form with name/email/phone/resume."""
        log.info("Generic fill — attempting to match fields by label")
        filled = self._fill_by_label()
        filled |= self._upload_file('input[type="file"]', "Resume")
        if filled:
            self._click_submit()
        return filled

    # ─── Shared helpers ───────────────────────────────────────────

    def _fill_input(self, selector: str, value: str) -> bool:
        """Fill a single input element by CSS selector."""
        try:
            el = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            if el.get_attribute("value"):
                return False  # already filled
            el.clear()
            el.send_keys(value)
            self.filled_fields.append(selector)
            log.debug(f"Filled {selector}")
            return True
        except Exception:
            return False

    def _fill_textareas(self) -> bool:
        """Fill any empty textarea with a default answer."""
        filled_any = False
        textareas = self.browser.find_elements(By.TAG_NAME, "textarea")
        for ta in textareas:
            if not ta.get_attribute("value"):
                ta.send_keys("Yes")
                filled_any = True
        return filled_any

    def _fill_by_label(self) -> bool:
        """Fill inputs by matching associated label text."""
        filled_any = False
        inputs = self.browser.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email'], input[type='tel'], textarea")
        for inp in inputs:
            if inp.get_attribute("value"):
                continue
            label = self._find_label_for(inp)
            if label:
                label_lower = label.lower()
                value = self._guess_value(label_lower)
                if value:
                    inp.send_keys(value)
                    filled_any = True
        return filled_any

    def _find_label_for(self, element) -> Optional[str]:
        """Find a visible label associated with an input."""
        try:
            # Check aria-label
            aria = element.get_attribute("aria-label")
            if aria:
                return aria
            # Check id-based label
            elem_id = element.get_attribute("id")
            if elem_id:
                labels = self.browser.find_elements(By.CSS_SELECTOR, f"label[for='{elem_id}']")
                if labels:
                    return labels[0].text.strip()
            # Check parent label
            parent = element.find_element(By.XPATH, "./ancestor::label")
            return parent.text.strip()
        except Exception:
            return None

    def _guess_value(self, label_text: str) -> str:
        """Return a sensible default value for a label."""
        if any(w in label_text for w in ["name", "full name"]):
            return self.config.get("name", "")
        if any(w in label_text for w in ["email", "e-mail"]):
            return self.config.get("email", "")
        if any(w in label_text for w in ["phone", "mobile", "tel"]):
            return self.config.get("phone", "")
        if any(w in label_text for w in ["resume", "cv", "upload"]):
            return "Resume"
        if any(w in label_text for w in ["cover", "letter"]):
            return "Cover Letter"
        if any(w in label_text for w in ["experience", "years"]):
            return "1"
        if any(w in label_text for w in ["sponsor"]):
            return "No"
        return "Yes"

    def _upload_file(self, selector: str, file_key: str, multiple: bool = False) -> bool:
        """Upload a file via an input[type=file] element."""
        file_path = self.uploads.get(file_key)
        if not file_path:
            return False
        try:
            if multiple:
                inputs = self.browser.find_elements(By.CSS_SELECTOR, selector)
                for inp in inputs:
                    if not inp.get_attribute("value"):
                        inp.send_keys(file_path)
                return True
            else:
                el = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                if not el.get_attribute("value"):
                    el.send_keys(file_path)
                    return True
                return False
        except Exception as e:
            log.error(f"File upload failed ({file_key}): {e}")
            return False

    def _click_submit(self) -> None:
        """Click any submit button or form-ending next button."""
        selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button[aria-label="Submit application"]',
        ]
        for sel in selectors:
            try:
                btn = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                btn.click()
                log.info("Clicked submit")
                time.sleep(1)
                return
            except Exception:
                continue
        log.warning("No submit button found")

    def _take_screenshot(self, label: str) -> None:
        """Capture a screenshot for debugging."""
        try:
            import os
            os.makedirs("screenshots", exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = f"screenshots/{label}_{ts}.png"
            self.browser.save_screenshot(path)
            log.info(f"Screenshot saved: {path}")
        except Exception as e:
            log.debug(f"Screenshot failed: {e}")
