"""
Murphy TX municipal utilities backend (Water).
Logs in with credentials from env; scrapes dashboard for balance and bill info.
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

CACHE_KEY_MURPHYTX = "murphytx"

MURPHYTX_UTILITIES_URL = "https://account.municipalonlinepayments.com/Account/Login?ReturnUrl=%2Fconnect%2Fauthorize%2Fcallback%3Fclient_id%3Dwww.municipalonlinepayments.com%26redirect_uri%3Dhttps%253A%252F%252Fmurphytx.municipalonlinepayments.com%252Fsignin-oidc%26response_type%3Dcode%2520id_token%2520token%26scope%3Dopenid%2520profile%2520email%26state%3DOpenIdConnect.AuthenticationProperties%253Dp39QDlAfC3Nv8ZsP078IaFLMIn4j-ZpGrTaC7IMopLc_BfKarx0hOdBF0H-RpeQv-9wYwa24-1EPLeCs4rX042uQDILIiYl_i5qsYhgnTE9K6lwoJ9yXPtbGDZ52lgBQ95sMeYczJRRYUsGzebclSvBclLoRcYoDMDjh_Gz6yDuWoP41uje9gvAaks9PxKr0ixQSZ1SD-dB_65l9niJ96z3YMQX0GInr7upnjohuPm6PrDvApKXxDCLqQ90WJ3X5Mqxn2G8G6jMjzqUmgyPVGAq7VhQ7o1re-f-0JFZp-5PRPdiPMcw5SeelQc6AbNmwUhp-0g%26response_mode%3Dform_post%26nonce%3D639053412683831109.NzZjNzMyOGItNGZmNi00NTMwLTk3YmEtN2FjOWU4NzljYzg4MzQzY2RhOGQtZDU0MS00NGU5LTgyZDEtZGE0NWMyMzRhNDc4%26site%3Dmurphytx%26x-client-SKU%3DID_NET461%26x-client-ver%3D5.5.0.0"
MURPHYTX_LOGIN_URL = "https://murphytx.municipalonlinepayments.com/murphytx/login"


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
    )


def _parse_due_date_from_bill_page(text: str) -> Optional[date]:
    """Extract due date from dashboard or bill text (e.g. 'Due date 1/15/2026', 'Due by Jan 15')."""
    if not text:
        return None
    # "Due date", "Due by", "Due:", "Payment due" followed by date
    patterns = [
        r"due\s+(?:date|by)?\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"due\s+(?:date|by)?\s*:?\s*(\w+\s+\d{1,2},?\s*\d{4})",
        r"due\s+(?:date|by)?\s*:?\s*(\d{1,2}-\d{1,2}-\d{2,4})",
        r"payment\s+due\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"(\d{1,2}/\d{1,2}/\d{2,4})\s*\(?due\)?",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            parsed = _parse_date_text(m.group(1))
            if parsed:
                return parsed
    if HAS_DATEUTIL:
        try:
            m = re.search(r"due\s+(?:date|by)?\s*:?\s*([^\n\r]+?)(?:\n|$)", text, re.I)
            if m:
                dt = dateutil_parser.parse(m.group(1).strip()[:50], default=datetime.now())
                return dt.date() if dt else None
        except Exception:
            pass
    return None


class MurphyTXBackend(UtilityBillDueBackend):
    """Murphy TX utility billing: login via env credentials, scrape dashboard."""

    def __init__(self, config: dict, logger=None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self._utility_type = (config.get("utility_type") or "water").lower()
        # Config loader already expands ${VAR} from .env; use those values directly.
        # If config has literal env var name (no ${}), resolve from os.environ.
        u = (config.get("username_env") or "").strip()
        p = (config.get("password_env") or "").strip()
        if u and u.replace("_", "").isalnum() and "@" not in u and "." not in u:
            u = os.environ.get(u, u)
        if p and p.replace("_", "").isalnum() and len(p) < 100:
            p = os.environ.get(p, p)
        self._username = u
        self._password = p
        self._headless = config.get("headless", True)
        cache_dir = config.get("cache_dir")
        self.cache_helper = CacheHelper(cache_dir, "utilities_bill_due")

    def get_bill_due_info(self) -> List[BillDueInfo]:
        """Login and scrape dashboard; return one BillDueInfo (water). Uses daily cache to avoid scraping every time."""
        if not self._username or not self._password:
            self.logger.warning(
                "Missing credentials: set username_env and password_env in config (e.g. ${MURPHYTX_USERNAME} from .env)"
            )
            return []

        # Return cached data if we have it for today
        cached = self.cache_helper.get_cached_content(CACHE_KEY_MURPHYTX)
        if cached:
            try:
                data = json.loads(cached)
                if isinstance(data, list) and data:
                    results = [_bill_due_info_from_dict(d) for d in data if isinstance(d, dict)]
                    if results:
                        self.logger.info("Murphy TX: using cached bill due data for today")
                        return results
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                self.logger.debug(f"Murphy TX: cache parse failed, will scrape: {e}")

        if not HAS_PLAYWRIGHT:
            self.logger.error("Playwright not installed; run: pip install playwright && playwright install chromium")
            return []

        self.logger.info(f"Murphy TX backend: fetching bill due info (utility_type={self._utility_type}, headless={self._headless})")

        results: List[BillDueInfo] = []
        with sync_playwright() as p:
            try:
                self.logger.info(f"Murphy TX: launching Chromium (headless={self._headless})")
                browser = p.chromium.launch(
                    headless=self._headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                context.set_default_timeout(15000)
                page = context.new_page()
            except Exception as e:
                self.logger.error(f"Murphy TX: failed to launch browser: {e}")
                return []

            try:
                page.goto(MURPHYTX_UTILITIES_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                body_text = page.inner_text("body")

                # If not on dashboard (no "Your current balance"), we need to log in
                if "Your current balance" not in body_text and "Welcome back" not in body_text:
                    # Click "Proceed to Sign-in/Register" if present (gets us to the login form)
                    if "Proceed to Sign-in/Register" in body_text:
                        self.logger.info("Murphy TX: clicking Proceed to Sign-in/Register")
                        try:
                            page.get_by_role("link", name="Proceed to Sign-in/Register").click()
                            page.wait_for_load_state("domcontentloaded")
                            page.wait_for_timeout(2000)
                        except Exception as e:
                            self.logger.debug(f"Murphy TX: click Proceed link: {e}")
                            try:
                                page.locator('a:has-text("Proceed to Sign-in/Register")').first.click()
                                page.wait_for_timeout(2000)
                            except Exception:
                                pass

                    # Now on login form: fill credentials and submit (from capture: login form has username/password inputs)
                    self.logger.info("Murphy TX: on login page, submitting credentials")
                    try:
                        username_sel = 'input[name="username"], input[type="email"], input[id*="user"], input[name="email"], input[type="text"]:not([type="hidden"])'
                        password_sel = 'input[name="password"], input[type="password"], input[id*="pass"]'
                        page.wait_for_selector(username_sel, timeout=12000)
                        page.fill(username_sel, self._username)
                        page.fill(password_sel, self._password)
                        login_btn_sel = "body > div > div.container-fluid > div > div > form > div:nth-child(4) > button"
                        try:
                            page.locator(login_btn_sel).click()
                        except Exception:
                            page.locator('button[type="submit"], input[type="submit"], button:has-text("Sign in"), button:has-text("Log in")').first.click()
                        page.wait_for_load_state("domcontentloaded", timeout=30000)
                        page.wait_for_timeout(2000)
                    except PlaywrightTimeout:
                        self.logger.warning("Murphy TX: timeout waiting after login")
                    except Exception as e:
                        self.logger.warning(f"Murphy TX: login submit failed: {e}")

                # After login we may land on home; navigate to utilities URL to see payment dashboard
                if "Your current balance" not in page.inner_text("body") and "Welcome back" not in page.inner_text("body"):
                    self.logger.info("Murphy TX: navigating to utilities URL for payment dashboard")
                    page.goto("https://murphytx.municipalonlinepayments.com/murphytx/utilities", wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

                # Wait for dashboard content (from capture: "Your current balance", "Welcome back")
                try:
                    page.wait_for_function(
                        "() => document.body.innerText.includes('Your current balance') || document.body.innerText.includes('Welcome back')",
                        timeout=15000,
                    )
                except PlaywrightTimeout:
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeout:
                    pass
                page.wait_for_timeout(1500)

                body_text = page.inner_text("body")
                current_balance = None
                payment_due = False
                amount_due_str = None
                current_bill_billed_date = None
                current_bill_amount = None
                last_payment_amount = None
                last_payment_date = None

                # Parse "Your current balance is $X.XX"
                balance_m = re.search(r"Your current balance is\s*\$?([\d,]+\.?\d*)", body_text, re.I)
                if balance_m:
                    try:
                        current_balance = float(balance_m.group(1).replace(",", ""))
                        payment_due = current_balance > 0
                        amount_due_str = f"${current_balance:.2f}" if current_balance else None
                    except ValueError:
                        pass

                # Parse Current bill card: "$335.55 billed 1/7/2026"
                bill_m = re.search(r"\$([\d,]+\.?\d*)\s+billed\s+(\d{1,2}/\d{1,2}/\d{2,4})", body_text)
                if bill_m:
                    try:
                        current_bill_amount = float(bill_m.group(1).replace(",", ""))
                        current_bill_billed_date = _parse_date_text(bill_m.group(2))
                    except ValueError:
                        pass

                # Parse Last Payment: "($335.55) paid 1/25/2026" or "paid 1/25/2026"
                last_m = re.search(r"(?:\(\$?([\d,]+\.?\d*)\)\s*)?paid\s+(\d{1,2}/\d{1,2}/\d{2,4})", body_text, re.I)
                if last_m:
                    if last_m.group(1):
                        try:
                            last_payment_amount = f"${float(last_m.group(1).replace(',', '')):.2f}"
                        except ValueError:
                            pass
                    last_payment_date = _parse_date_text(last_m.group(2))

                # Parse due date from dashboard text (shown when bill is due; may be absent when balance is zero)
                due_date = _parse_due_date_from_bill_page(body_text)

                results.append(
                    BillDueInfo(
                        utility_type=self._utility_type,
                        source="Murphy TX",
                        due_date=due_date,
                        amount_due=amount_due_str,
                        payment_due=payment_due,
                        current_balance=current_balance,
                        current_bill_billed_date=current_bill_billed_date,
                        last_payment_amount=last_payment_amount,
                        last_payment_date=last_payment_date,
                        raw_status=f"balance={current_balance}" if current_balance is not None else None,
                    )
                )
                self.logger.info(f"Murphy TX: finished, payment_due={payment_due}")
            except PlaywrightTimeout as e:
                self.logger.warning(f"Murphy TX: timeout: {e}")
            except Exception as e:
                self.logger.exception(f"Murphy TX: scrape error: {e}")
            finally:
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass

        # Save to daily cache so we don't scrape again until tomorrow
        if results:
            try:
                cache_content = json.dumps([_bill_due_info_to_dict(r) for r in results])
                self.cache_helper.save_to_cache(CACHE_KEY_MURPHYTX, cache_content)
                self.logger.info("Murphy TX: saved bill due data to daily cache")
            except Exception as e:
                self.logger.debug(f"Murphy TX: failed to save cache: {e}")

        return results
