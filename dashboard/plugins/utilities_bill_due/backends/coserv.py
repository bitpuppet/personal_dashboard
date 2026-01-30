"""
CoServ (gas) backend via SmartHub.
Logs in at https://coserv.smarthub.coop/ui/#/login with Email/Password;
scrapes HOME dashboard for Current Bill Amount, Due Date, Last Payment, usage (therms).
Uses daily file cache so we do not scrape on every load.
"""
import json
import os
import re
import logging
from datetime import date, datetime
from typing import List, Optional

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

from dashboard.core.cache_helper import CacheHelper
from .base import BillDueInfo, UtilityBillDueBackend

COSERV_LOGIN_URL = "https://coserv.smarthub.coop/ui/#/login"
CACHE_KEY_COSERV = "coserv"

# Month names for usage parsing (Usage Comparison: "Jan 2026568" -> latest month)
_MONTH_NAMES = r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_MONTH_TO_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_usage_from_body(body_text: str, unit: str = "units") -> Optional[str]:
    """Find all 'Month YYYY' + digits on page and return usage for the latest month, e.g. '568 kWh' or '120 therms'."""
    if not body_text:
        return None
    pattern = re.compile(
        rf"({_MONTH_NAMES})\s*(\d{{4}})\s*(\d+)",
        re.I,
    )
    matches = []
    for m in pattern.finditer(body_text):
        month_str = m.group(1).lower()
        year = int(m.group(2))
        value = m.group(3)
        month_num = _MONTH_TO_NUM.get(month_str)
        if month_num is not None and value.isdigit():
            matches.append((year, month_num, value))
    if not matches:
        m = re.search(r"(\d+)\s*(?:kWh|units?)", body_text, re.I)
        if m:
            return f"{m.group(1)} {unit}"
        return None
    matches.sort(key=lambda x: (x[0], x[1]))
    _, _, value = matches[-1]
    return f"{value} {unit}"


def _parse_currency(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"[\$\(]?\s*([\d,]+\.?\d*)\s*\)?", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_date_text(text: str) -> Optional[date]:
    if not text:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", text)
    if not m:
        if HAS_DATEUTIL:
            try:
                dt = dateutil_parser.parse(text[:30], default=datetime.now())
                return dt.date() if dt else None
            except Exception:
                pass
        return None
    try:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        return date(y, mo, d)
    except (ValueError, TypeError):
        return None


def _parse_date_month_name(text: str) -> Optional[date]:
    if not text:
        return None
    text = text.strip()
    if HAS_DATEUTIL:
        try:
            dt = dateutil_parser.parse(text[:50], default=datetime.now())
            return dt.date() if dt else None
        except Exception:
            pass
    m = re.search(r"(\w+)\s+(\d{1,2}),?\s*(\d{4})", text)
    if not m:
        return None
    try:
        return dateutil_parser.parse(f"{m.group(1)} {m.group(2)}, {m.group(3)}").date()
    except Exception:
        return None


def _parse_due_date_from_text(text: str) -> Optional[date]:
    if not text:
        return None
    m = re.search(r"Next Auto Pay Due Date\s+(\w+\s+\d{1,2},?\s*\d{4})", text, re.I)
    if m:
        parsed = _parse_date_month_name(m.group(1))
        if parsed:
            return parsed
    for pat in [
        r"due\s+(?:date|by)?\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"due\s+(?:date|by)?\s*:?\s*(\w+\s+\d{1,2},?\s*\d{4})",
        r"payment\s+due\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            parsed = _parse_date_text(m.group(1)) or _parse_date_month_name(m.group(1))
            if parsed:
                return parsed
    return None


def _bill_due_info_to_dict(item: BillDueInfo) -> dict:
    return {
        "utility_type": item.utility_type,
        "source": item.source,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "amount_due": item.amount_due,
        "payment_due": item.payment_due,
        "current_balance": item.current_balance,
        "current_bill_billed_date": item.current_bill_billed_date.isoformat() if item.current_bill_billed_date else None,
        "last_payment_amount": item.last_payment_amount,
        "last_payment_date": item.last_payment_date.isoformat() if item.last_payment_date else None,
        "raw_status": item.raw_status,
        "usage": getattr(item, "usage", None),
    }


def _bill_due_info_from_dict(d: dict) -> BillDueInfo:
    def parse_date(s: Optional[str]) -> Optional[date]:
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return BillDueInfo(
        utility_type=d.get("utility_type"),
        source=d.get("source"),
        due_date=parse_date(d.get("due_date")),
        amount_due=d.get("amount_due"),
        payment_due=bool(d.get("payment_due")),
        current_balance=d.get("current_balance"),
        current_bill_billed_date=parse_date(d.get("current_bill_billed_date")),
        last_payment_amount=d.get("last_payment_amount"),
        last_payment_date=parse_date(d.get("last_payment_date")),
        raw_status=d.get("raw_status"),
        usage=d.get("usage"),
    )


class CoServBackend(UtilityBillDueBackend):
    """CoServ (gas) via SmartHub: login with Email/Password, scrape HOME dashboard."""

    def __init__(self, config: dict, logger=None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self._utility_type = (config.get("utility_type") or "gas").lower()
        u = (config.get("username_env") or "").strip()
        p = (config.get("password_env") or "").strip()
        if u and u.replace("_", "").replace("-", "").isalnum() and "@" not in u and "." not in u:
            u = os.environ.get(u, u)
        if p and p.replace("_", "").replace("-", "").isalnum() and len(p) < 100:
            p = os.environ.get(p, p)
        self._username = u
        self._password = p
        self._headless = config.get("headless", True)
        cache_dir = config.get("cache_dir")
        self.cache_helper = CacheHelper(cache_dir, "utilities_bill_due")

    def get_bill_due_info(self) -> List[BillDueInfo]:
        """Login and scrape SmartHub HOME dashboard; return one BillDueInfo (gas). Uses daily cache."""
        if not self._username or not self._password:
            self.logger.warning(
                "Missing credentials: set username_env and password_env in config (e.g. ${COSERV_USERNAME} from .env)"
            )
            return []

        cached = self.cache_helper.get_cached_content(CACHE_KEY_COSERV)
        if cached:
            try:
                data = json.loads(cached)
                if isinstance(data, list) and data:
                    results = [_bill_due_info_from_dict(d) for d in data if isinstance(d, dict)]
                    if results:
                        self.logger.info("CoServ: using cached bill due data for today")
                        return results
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                self.logger.debug(f"CoServ: cache parse failed, will scrape: {e}")

        if not HAS_PLAYWRIGHT:
            self.logger.error("Playwright not installed; run: pip install playwright && playwright install chromium")
            return []

        self.logger.info(f"CoServ backend: fetching bill due info (headless={self._headless})")
        results: List[BillDueInfo] = []

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    headless=self._headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                context.set_default_timeout(20000)
                page = context.new_page()
            except Exception as e:
                self.logger.error(f"CoServ: failed to launch browser: {e}")
                return []

            try:
                page.goto(COSERV_LOGIN_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                email_sel = '#mat-input-0, input[aria-label="Email"]'
                password_sel = '#mat-input-1, input[aria-label="Password"], input[type="password"]'
                try:
                    page.wait_for_selector(email_sel, timeout=10000)
                    page.fill(email_sel, self._username)
                    page.fill(password_sel, self._password)
                    page.locator('button:has-text("Sign In"), button[type="submit"]').first.click()
                except PlaywrightTimeout:
                    self.logger.warning("CoServ: timeout waiting for login form")
                except Exception as e:
                    self.logger.warning(f"CoServ: login fill/click failed: {e}")

                page.wait_for_load_state("domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                try:
                    page.wait_for_function(
                        "() => document.body.innerText.includes('Current Bill Amount') || document.body.innerText.includes('Past Due Balance')",
                        timeout=15000,
                    )
                except PlaywrightTimeout:
                    pass
                page.wait_for_timeout(1500)

                body_text = page.inner_text("body")
                current_balance = None
                payment_due = False
                amount_due_str = None
                due_date = None
                last_payment_amount = None
                last_payment_date = None
                usage_str = None

                bill_m = re.search(r"\$([\d,]+\.?\d*)\s+Current Bill Amount|Current Bill Amount\s+\$([\d,]+\.?\d*)", body_text, re.I | re.DOTALL)
                if bill_m:
                    g = bill_m.group(1) or bill_m.group(2)
                    if g:
                        try:
                            current_balance = float(g.replace(",", ""))
                            payment_due = current_balance > 0
                            amount_due_str = f"${current_balance:.2f}"
                        except ValueError:
                            pass

                past_due_m = re.search(r"\$([\d,]+\.?\d*)\s+Past Due Balance|Past Due Balance\s+\$([\d,]+\.?\d*)", body_text, re.I | re.DOTALL)
                if past_due_m:
                    g = past_due_m.group(1) or past_due_m.group(2)
                    if g:
                        try:
                            past_due = float(g.replace(",", ""))
                            if past_due > 0:
                                payment_due = True
                        except ValueError:
                            pass

                due_date = _parse_due_date_from_text(body_text)

                last_date_m = re.search(r"Last Payment.*?on\s+(\w+\s+\d{1,2},?\s*\d{4})|PAID on\s+(\w+\s+\d{1,2},?\s*\d{4})", body_text, re.I)
                if last_date_m:
                    last_payment_date = _parse_date_month_name(last_date_m.group(1) or last_date_m.group(2))
                last_amt_m = re.search(r"\$([\d,]+\.?\d*)\s+Last Payment|Last Payment.*?\$([\d,]+\.?\d*)", body_text, re.I | re.DOTALL)
                if last_amt_m:
                    g = last_amt_m.group(1) or last_amt_m.group(2)
                    if g:
                        try:
                            last_payment_amount = f"${float(g.replace(',', '')):.2f}"
                        except ValueError:
                            pass

                usage_unit = "therms" if "therm" in body_text.lower() else "units"
                usage_str = _parse_usage_from_body(body_text, unit=usage_unit)

                results.append(
                    BillDueInfo(
                        utility_type=self._utility_type,
                        source="CoServ",
                        due_date=due_date,
                        amount_due=amount_due_str,
                        payment_due=payment_due,
                        current_balance=current_balance,
                        current_bill_billed_date=None,
                        last_payment_amount=last_payment_amount,
                        last_payment_date=last_payment_date,
                        raw_status=f"balance={current_balance}" if current_balance is not None else None,
                        usage=usage_str,
                    )
                )
                self.logger.info(f"CoServ: finished, payment_due={payment_due}")
            except PlaywrightTimeout as e:
                self.logger.warning(f"CoServ: timeout: {e}")
            except Exception as e:
                self.logger.exception(f"CoServ: scrape error: {e}")
            finally:
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass

        if results:
            try:
                cache_content = json.dumps([_bill_due_info_to_dict(r) for r in results])
                self.cache_helper.save_to_cache(CACHE_KEY_COSERV, cache_content)
                self.logger.info("CoServ: saved bill due data to daily cache")
            except Exception as e:
                self.logger.debug(f"CoServ: failed to save cache: {e}")

        return results
