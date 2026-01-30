"""
Farmers Electric Cooperative (electric) backend via SmartHub.
Logs in at https://farmerselectric.smarthub.coop/ui/#/login with Email/Password;
scrapes HOME dashboard for Current Bill Amount, Due Date, Last Payment, etc.
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

FARMERSELECTRIC_LOGIN_URL = "https://farmerselectric.smarthub.coop/ui/#/login"
CACHE_KEY_FARMERSELECTRIC = "farmerselectric"

# Month names for usage parsing (Usage Comparison: "Jan 2026568" -> latest month's kWh)
_MONTH_NAMES = r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_MONTH_TO_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_usage_from_body(body_text: str) -> Optional[str]:
    """Find all 'Month YYYY' + digits (kWh) on page and return usage for the latest month, e.g. '568 kWh'."""
    if not body_text:
        return None
    # Match "Jan 2025732", "Jan 2026568", "Feb 2026123" etc. (month name, year, digits)
    pattern = re.compile(
        rf"({_MONTH_NAMES})\s*(\d{{4}})\s*(\d+)",
        re.I,
    )
    matches = []
    for m in pattern.finditer(body_text):
        month_str = m.group(1).lower()
        year = int(m.group(2))
        kWh = m.group(3)
        month_num = _MONTH_TO_NUM.get(month_str)
        if month_num is not None and kWh.isdigit():
            matches.append((year, month_num, kWh))
    if not matches:
        # Fallback: any "NNN kWh" or "NNN" near "kWh"
        m = re.search(r"(\d+)\s*kWh", body_text, re.I)
        if m:
            return f"{m.group(1)} kWh"
        return None
    # Take latest (year, month)
    matches.sort(key=lambda x: (x[0], x[1]))
    _, _, kWh = matches[-1]
    return f"{kWh} kWh"


def _parse_currency(text: str) -> Optional[float]:
    """Parse $X.XX or (X.XX) from text. Returns float or None."""
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
    """Parse date from text like 1/7/2026 or 1/25/2026."""
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
    """Parse 'February 3, 2026' or 'January 2, 2026' (month name + day + year)."""
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
    """Extract due date from SmartHub dashboard text (e.g. 'Next Auto Pay Due Date February 3, 2026')."""
    if not text:
        return None
    # SmartHub: "Next Auto Pay Due Date February 3, 2026"
    m = re.search(r"Next Auto Pay Due Date\s+(\w+\s+\d{1,2},?\s*\d{4})", text, re.I)
    if m:
        parsed = _parse_date_month_name(m.group(1))
        if parsed:
            return parsed
    # Fallbacks: "due date", "due by", "payment due"
    patterns = [
        r"due\s+(?:date|by)?\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"due\s+(?:date|by)?\s*:?\s*(\w+\s+\d{1,2},?\s*\d{4})",
        r"payment\s+due\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            parsed = _parse_date_text(m.group(1)) or _parse_date_month_name(m.group(1))
            if parsed:
                return parsed
    return None


def _bill_due_info_to_dict(item: BillDueInfo) -> dict:
    """Serialize one BillDueInfo to a JSON-safe dict (dates as ISO strings)."""
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
    """Deserialize one dict (from JSON cache) back to BillDueInfo."""
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


class FarmersElectricBackend(UtilityBillDueBackend):
    """Farmers Electric Cooperative (electric) via SmartHub: login with Email/Password, scrape HOME dashboard."""

    def __init__(self, config: dict, logger=None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self._utility_type = (config.get("utility_type") or "electric").lower()
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
        """Login and scrape SmartHub HOME dashboard; return one BillDueInfo (electric). Uses daily cache."""
        if not self._username or not self._password:
            self.logger.warning(
                "Missing credentials: set username_env and password_env in config (e.g. ${FARMERSELECTRIC_USERNAME} from .env)"
            )
            return []

        cached = self.cache_helper.get_cached_content(CACHE_KEY_FARMERSELECTRIC)
        if cached:
            try:
                data = json.loads(cached)
                if isinstance(data, list) and data:
                    results = [_bill_due_info_from_dict(d) for d in data if isinstance(d, dict)]
                    if results:
                        self.logger.info("Farmers Electric: using cached bill due data for today")
                        return results
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                self.logger.debug(f"Farmers Electric: cache parse failed, will scrape: {e}")

        if not HAS_PLAYWRIGHT:
            self.logger.error("Playwright not installed; run: pip install playwright && playwright install chromium")
            return []

        self.logger.info(f"Farmers Electric backend: fetching bill due info (headless={self._headless})")
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
                self.logger.error(f"Farmers Electric: failed to launch browser: {e}")
                return []

            try:
                page.goto(FARMERSELECTRIC_LOGIN_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                # Login form: Angular Material inputs (aria-label=Email / Password)
                email_sel = '#mat-input-0, input[aria-label="Email"]'
                password_sel = '#mat-input-1, input[aria-label="Password"], input[type="password"]'
                try:
                    page.wait_for_selector(email_sel, timeout=10000)
                    page.fill(email_sel, self._username)
                    page.fill(password_sel, self._password)
                    page.locator('button:has-text("Sign In"), button[type="submit"]').first.click()
                except PlaywrightTimeout:
                    self.logger.warning("Farmers Electric: timeout waiting for login form")
                except Exception as e:
                    self.logger.warning(f"Farmers Electric: login fill/click failed: {e}")

                page.wait_for_load_state("domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                # Wait for HOME dashboard (Current Bill Amount or Past Due Balance)
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

                # From captured session: amounts appear above their labels (e.g. "$80.00" then "Current Bill Amount")
                # Current Bill Amount: "$80.00" then "Current Bill Amount"
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

                # Past Due Balance: "$0.00" then "Past Due Balance"
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

                # Due date: "Next Auto Pay Due Date February 3, 2026"
                due_date = _parse_due_date_from_text(body_text)

                # Last Payment: "$101.00" then "Last Payment Amount"; date from "PAID on January 2, 2026"
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

                # Usage: find latest month in Usage Comparison (e.g. "Jan 2026568", "Feb 2026123") and use that kWh
                usage_str = _parse_usage_from_body(body_text)

                results.append(
                    BillDueInfo(
                        utility_type=self._utility_type,
                        source="Farmers Electric",
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
                self.logger.info(f"Farmers Electric: finished, payment_due={payment_due}")
            except PlaywrightTimeout as e:
                self.logger.warning(f"Farmers Electric: timeout: {e}")
            except Exception as e:
                self.logger.exception(f"Farmers Electric: scrape error: {e}")
            finally:
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass

        if results:
            try:
                cache_content = json.dumps([_bill_due_info_to_dict(r) for r in results])
                self.cache_helper.save_to_cache(CACHE_KEY_FARMERSELECTRIC, cache_content)
                self.logger.info("Farmers Electric: saved bill due data to daily cache")
            except Exception as e:
                self.logger.debug(f"Farmers Electric: failed to save cache: {e}")

        return results
