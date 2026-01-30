"""
Google Classroom scraper for one student using Playwright.
Uses a persistent browser profile (user_data_dir) so the user logs in once;
then scrapes classroom.google.com for due assignments.
"""
import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from dateutil import parser as dateutil_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


def _expand_path(path_str: str) -> str:
    return os.path.expanduser(os.path.expandvars(path_str))


def _parse_due_text(text: str) -> Optional[datetime]:
    """Try to parse due date/time from Classroom UI text (e.g. 'Due Jan 15', 'Due 11:59 PM')."""
    if not text or not text.strip():
        return None
    text = text.strip()
    # Remove "Due " prefix if present
    if text.lower().startswith("due "):
        text = text[4:].strip()
    if not text:
        return None
    try:
        if HAS_DATEUTIL:
            dt = dateutil_parser.parse(text, default=datetime.now().replace(hour=23, minute=59, second=0, microsecond=0))
            return dt
    except Exception:
        pass
    # Fallback: try "M/D" or "Jan 15"
    for fmt in ("%b %d", "%B %d", "%m/%d", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(text[:20].strip(), fmt)
            dt = dt.replace(year=datetime.now().year, hour=23, minute=59, second=0, microsecond=0)
            return dt
        except ValueError:
            continue
    return None


class ClassroomScraper:
    """
    One student: Playwright persistent context + scrape classroom.google.com
    for due assignments. Same interface as ClassroomClient (get_due_assignments).
    """

    def __init__(
        self,
        student_name: str,
        profile_path: str,
        logger: Optional[logging.Logger] = None,
    ):
        self.student_name = student_name
        self.profile_path = _expand_path(profile_path)
        self.logger = logger or logging.getLogger(__name__)

    def get_due_assignments(
        self,
        include_overdue: bool = True,
        fetch_submission_status: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Open classroom.google.com with persistent profile, scrape To-do/stream
        for assignments with due dates. Returns same shape as ClassroomClient.
        """
        if not HAS_PLAYWRIGHT:
            self.logger.error("Playwright not installed; run: pip install playwright && playwright install chromium")
            return []
        self.logger.info(f"Classroom scraper: starting for {self.student_name} (profile={self.profile_path})")

        profile = Path(self.profile_path)
        if not profile.is_dir():
            self.logger.warning(
                f"Profile dir not found for {self.student_name}: {self.profile_path}. "
                "Log in once with a browser using this user_data_dir."
            )

        results: List[Dict[str, Any]] = []
        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=self.profile_path,
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 800},
                    timeout=30000,
                )
            except Exception as e:
                self.logger.error(f"Failed to launch browser for {self.student_name}: {e}")
                return []

            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(15000)
                page.goto("https://classroom.google.com/", wait_until="domcontentloaded")

                # First-time setup: if on login page, wait for redirect back to Classroom after login
                # so the profile is saved when we close the context
                if "accounts.google.com" in page.url:
                    self.logger.info(
                        f"First-time setup for {self.student_name}: log in now in the browser. "
                        "Waiting up to 2 minutes; profile will be saved when done."
                    )
                    try:
                        page.wait_for_url("**/classroom.google.com/**", timeout=120000)
                    except PlaywrightTimeout:
                        self.logger.warning(
                            f"Timeout waiting for login for {self.student_name}. "
                            "Log in in the browser and run refresh again; profile will be saved."
                        )
                # Wait for app to load: common Classroom container or to-do
                try:
                    page.wait_for_selector(
                        "[data-identifier], [jsname], [role='main']",
                        timeout=15000,
                    )
                except PlaywrightTimeout:
                    page.wait_for_load_state("networkidle", timeout=10000)
                # Give a moment for dynamic content
                page.wait_for_timeout(2000)

                # Scrape assignment-like items from the stream / to-do area
                # Google Classroom uses various structures; try multiple strategies
                items = self._scrape_assignments_from_page(page)
                today = date.today()
                for item in items:
                    due_dt = item.get("due_datetime")
                    if due_dt is None:
                        continue
                    if not include_overdue and due_dt.date() < today:
                        continue
                    item["student_name"] = self.student_name
                    if item.get("status") is None and fetch_submission_status:
                        item["status"] = item.get("status")  # already set by scraper if visible
                    results.append(item)
                self.logger.info(f"Classroom scraper: finished for {self.student_name}, {len(results)} assignment(s)")
            except PlaywrightTimeout as e:
                self.logger.warning(f"Timeout scraping Classroom for {self.student_name}: {e}")
            except Exception as e:
                self.logger.exception(f"Scrape error for {self.student_name}: {e}")
            finally:
                try:
                    context.close()
                except Exception:
                    pass

        return results

    def _scrape_assignments_from_page(self, page) -> List[Dict[str, Any]]:
        """Extract assignment-like rows from the current page. Tolerates DOM changes."""
        items: List[Dict[str, Any]] = []
        # Strategy 1: look for list items that look like assignments (course + title + due)
        try:
            # Common pattern: stream items or to-do cards
            locators = [
                page.locator("[data-identifier]").filter(has_text="Due"),
                page.locator("[jsname='tbTQkd']"),  # known in some versions
                page.locator("div[role='listitem']").filter(has_text="Due"),
                page.locator("a[href*='/a/']").filter(has_text="Due"),
            ]
            seen = set()
            for loc in locators:
                try:
                    for i in range(loc.count()):
                        if i > 50:
                            break
                        el = loc.nth(i)
                        try:
                            text = el.inner_text()
                            if not text or text in seen:
                                continue
                            seen.add(text)
                            parsed = self._parse_assignment_block(text)
                            if parsed:
                                items.append(parsed)
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as e:
            self.logger.debug(f"Selector strategy failed: {e}")

        # Strategy 2: get all links that look like assignment links and nearby due text
        try:
            links = page.locator("a[href*='classroom.google.com'][href*='/a/']").all()
            for link in links[:30]:
                try:
                    href = link.get_attribute("href") or ""
                    title = link.inner_text().strip() or "Assignment"
                    # Try to find due date in parent or sibling
                    parent = link.locator("xpath=..")
                    parent_text = parent.inner_text() if parent.count() else ""
                    due_dt = _parse_due_text(parent_text) or self._extract_due_from_text(parent_text)
                    course = self._extract_course_from_context(page, link)
                    key = (title, due_dt)
                    if key not in seen:
                        seen.add(key)
                        items.append({
                            "course_name": course or "—",
                            "title": title[:200],
                            "due_datetime": due_dt,
                            "status": None,
                        })
                except Exception:
                    continue
        except Exception:
            pass

        # Dedupe by (course, title, due)
        by_key: Dict[tuple, Dict[str, Any]] = {}
        for it in items:
            k = (it.get("course_name"), it.get("title"), it.get("due_datetime"))
            if k not in by_key or (it.get("due_datetime") and not by_key[k].get("due_datetime")):
                by_key[k] = it
        return list(by_key.values())

    def _parse_assignment_block(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse a block of text that may contain course name, title, and due date."""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            return None
        due_dt = None
        due_line = None
        for i, line in enumerate(lines):
            if "due" in line.lower():
                due_dt = _parse_due_text(line) or self._extract_due_from_text(line)
                due_line = i
                break
        if due_dt is None:
            for line in lines:
                due_dt = _parse_due_text(line) or self._extract_due_from_text(line)
                if due_dt:
                    break
        title = lines[0] if lines else "Assignment"
        course = "—"
        if len(lines) >= 2 and due_line is not None and due_line > 1:
            course = lines[1]
        elif len(lines) >= 2:
            course = lines[1]
        status = None
        for line in lines:
            if "turn in" in line.lower() or "turned in" in line.lower():
                status = "Turned in"
                break
            if "missing" in line.lower():
                status = "Missing"
                break
        return {
            "course_name": course[:100],
            "title": title[:200],
            "due_datetime": due_dt,
            "status": status,
        }

    def _extract_due_from_text(self, text: str) -> Optional[datetime]:
        """Try to find a date/time pattern in text."""
        if not text:
            return None
        # "Due Jan 15, 11:59 PM" or "1/15" or "Jan 15"
        m = re.search(r"due\s+(.+?)(?:\n|$)", text, re.I)
        if m:
            return _parse_due_text(m.group(1))
        m = re.search(r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)", text)
        if m:
            return _parse_due_text(m.group(1))
        m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}", text, re.I)
        if m:
            return _parse_due_text(m.group(0))
        return None

    def _extract_course_from_context(self, page, link_handle) -> Optional[str]:
        """Try to get course name from surrounding context (optional)."""
        try:
            parent = link_handle.locator("xpath=./ancestor::*[.//*[contains(text(),'Due')]][1]")
            if parent.count():
                t = parent.first.inner_text()
                for line in t.split("\n"):
                    if "due" not in line.lower() and len(line) > 2 and len(line) < 80:
                        return line.strip()
        except Exception:
            pass
        return None
