import urllib.parse
import time
import os
import sys
import re
import random
from typing import List, Dict, Any, Callable, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.browser.engine import BrowserManager
from src.browser.actions import HumanActions
from src.scraper.parser import JobParser
from src.storage.db import DatabaseManager
from src.storage.local import StorageManager


class LinkedInScraper:
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.manager = BrowserManager()
        self.db = DatabaseManager()
        self.storage = StorageManager()
        self.log = log_callback or print

    NAV_TIMEOUT_MS = 45000

    def _goto(self, page, url: str, what: str) -> bool:
        """Navigate with an explicit timeout; never hang the worker silently."""
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT_MS)
            return True
        except Exception as e:
            self.log(f"❌ Navigation to {what} timed out ({e}). Check connection/selectors.")
            return False

    def _extract_post_permalink(self, card, page) -> Optional[str]:
        """Extract the exact permalink of a feed post card via anchors or control menu."""
        try:
            # 1. Direct attribute or anchor scan on the card
            for a in card.query_selector_all("a[href]"):
                h = (a.get_attribute("href") or "").strip()
                if not h:
                    continue
                m_act = re.search(r'activity:(\d+)|activity-(\d+)', h)
                if m_act:
                    act_id = m_act.group(1) or m_act.group(2)
                    return f"https://www.linkedin.com/feed/update/urn:li:activity:{act_id}/"

                if "/feed/update/" in h or ("/posts/" in h and "/in/" not in h) or "lnkd.in/p/" in h:
                    clean = h.split("?")[0]
                    if not clean.startswith("http"):
                        clean = f"https://www.linkedin.com{clean}"
                    return clean

            # 2. Check DOM data attributes for activity URN
            try:
                urn_val = card.evaluate('''el => {
                    const target = el.querySelector('[data-urn*="activity"], [data-activity-urn], [data-ch-urn*="activity"], [data-id*="activity"]');
                    if (target) {
                        return target.getAttribute('data-urn') || target.getAttribute('data-activity-urn') || target.getAttribute('data-ch-urn') || target.getAttribute('data-id');
                    }
                    return el.getAttribute('data-urn') || el.getAttribute('data-id') || null;
                }''')
                if urn_val:
                    m_u = re.search(r'urn:li:activity:(\d+)', urn_val)
                    if m_u:
                        return f"https://www.linkedin.com/feed/update/urn:li:activity:{m_u.group(1)}/"
            except Exception:
                pass

            # 3. Native click on card's control menu to copy verified post permalink
            btn = card.query_selector('button[aria-label*="Open control menu"], button[aria-label*="control menu"]')
            if not btn:
                return None

            page.evaluate('''() => {
                window.__copiedLink = null;
                if (navigator.clipboard) {
                    navigator.clipboard.writeText = async (t) => {
                        window.__copiedLink = t;
                        return Promise.resolve();
                    };
                }
            }''')
            btn.click(timeout=1500)
            page.wait_for_timeout(350)

            copy_btn = page.query_selector('[role="menuitem"]:has-text("Copy link to post")')
            if copy_btn:
                copy_btn.click(timeout=1500)
                page.wait_for_timeout(250)
                url = page.evaluate('() => window.__copiedLink')
                if url:
                    u_str = str(url).strip()
                    m_act = re.search(r'activity:(\d+)|activity-(\d+)', u_str)
                    if m_act:
                        act_id = m_act.group(1) or m_act.group(2)
                        return f"https://www.linkedin.com/feed/update/urn:li:activity:{act_id}/"
                    return u_str
            else:
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        return None

    def _interruptible_sleep(self, seconds: float, should_stop: Optional[Callable[[], bool]] = None, step: float = 0.25) -> bool:
        """Sleeps for `seconds` in short increments so stop requests take effect immediately.
        Returns True if stop was requested during sleep, False otherwise."""
        end_time = time.time() + max(0.0, seconds)
        while time.time() < end_time:
            if should_stop and should_stop():
                return True
            time.sleep(min(step, max(0.0, end_time - time.time())))
        return bool(should_stop and should_stop())

    def ensure_logged_in(self, page, should_stop: Optional[Callable[[], bool]] = None) -> bool:
        """Checks if user is logged into LinkedIn; waits if manual login is needed."""
        self.log("🔑 Checking LinkedIn login status...")
        if not self._goto(page, "https://www.linkedin.com/feed/", "LinkedIn feed"):
            return False
        if self._interruptible_sleep(3.0, should_stop):
            return False

        current_url = page.url.lower()
        if "login" in current_url or "signup" in current_url or "authwall" in current_url:
            self.log("⚠️ Not logged in yet! Please log into LinkedIn in the open Chrome window.")
            self.log("⏳ The scraper will automatically resume once you log in...")

            # Wait up to 3 minutes for user to log in manually in the browser
            for waited in range(36):
                time.sleep(5)
                if should_stop and should_stop():
                    self.log("🛑 Stop requested during login wait — aborting.")
                    return False
                if "feed" in page.url.lower() or "mynetwork" in page.url.lower():
                    self.log("✅ Login detected! Continuing...")
                    return True
                if waited % 3 == 2:
                    self.log(f"⏳ Still waiting for LinkedIn login... ({(waited + 1) * 5}s elapsed)")
            self.log("❌ Login wait timed out after 3 minutes. Aborting scrape.")
            return False
        else:
            self.log("✅ Already logged in via persistent session!")
            return True

    def search_posts(self, page, query_text: str, location: str = "", limit: int = 20,
                     progress_callback: Optional[Callable[[int, int, str], None]] = None,
                     should_stop: Optional[Callable[[], bool]] = None,
                     domain_keywords: Optional[List[str]] = None,
                     exclude_keywords: Optional[List[str]] = None,
                     max_yoe: Optional[int] = None,
                     target_seniority: Optional[str] = None,
                     target_roles: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Yield-driven scraper: Collects up to `limit` 100% unique, un-scraped hiring leads.
        Deduplicates in real time against applications.db (cross-session).
        When a search feed reaches the bottom or repeats, seamlessly pivots to the next
        role synonym or search variation in the cascade within the same browser window.
        """
        from src.scraper.query_builder import LinkedInQueryBuilder

        if max_yoe:
            self.log(f"🎯 Candidate Criteria: Max {max_yoe} YOE" + (f", Target {target_seniority}" if target_seniority else ""))
        if exclude_keywords:
            self.log(f"🚫 Negative Exclusions: {', '.join(exclude_keywords[:5])}")

        # 1. Load historical hashes for instantaneous cross-session duplicate suppression
        existing_hashes = self.db.get_existing_job_hashes()
        self.log(f"🧠 Database deduplication active ({len(existing_hashes)} previously known records indexed).")

        # 2. Build multi-query cascade
        url_override = os.getenv("LINKEDIN_TARGET_URL") or os.getenv("EASYAPPLY_SELENIUM_SEARCH_URL")
        if url_override and url_override.strip():
            cascade = [{
                "label": "Custom URL Target",
                "url": url_override.strip(),
                "keywords_for_filter": LinkedInQueryBuilder.extract_core_keywords(query_text)
            }]
        elif query_text.startswith("http://") or query_text.startswith("https://"):
            cascade = [{
                "label": "Direct URL Target",
                "url": query_text.strip(),
                "keywords_for_filter": LinkedInQueryBuilder.extract_core_keywords(query_text)
            }]
        else:
            cascade = LinkedInQueryBuilder.build_posts_search_cascade(query_text, location=location, target_roles=target_roles)

        self.log(f"🔀 Search cascade prepared with {len(cascade)} search variations.")
        posts_found: List[Dict[str, Any]] = []
        session_seen_ids = set()
        page_load_wait = int(os.getenv("PAGE_LOAD_WAIT_MS", 5000)) / 1000
        scroll_delay = int(os.getenv("SCROLL_DELAY_MS", 3000)) / 1000
        max_stage_scrolls = int(os.getenv("MAX_SCROLL_ATTEMPTS", 60))
        max_global_scrolls = int(os.getenv("MAX_GLOBAL_SCROLLS", 140))
        session_start_time = time.time()
        max_session_duration = int(os.getenv("MAX_SCRAPE_DURATION_S", 600))  # 10 minute safety limit
        total_scrolls = 0

        for stage_idx, stage in enumerate(cascade):
            if len(posts_found) >= limit:
                break
            if should_stop and should_stop():
                self.log("🛑 Stop requested — halting search cascade.")
                break
            if total_scrolls >= max_global_scrolls:
                self.log(f"🛡️ Safety limit reached ({total_scrolls}/{max_global_scrolls} total scrolls across cascade). Stopping to protect LinkedIn account.")
                break
            if (time.time() - session_start_time) >= max_session_duration:
                self.log(f"🛡️ Max search duration ({max_session_duration}s) reached. Stopping to protect LinkedIn account.")
                break

            stage_label = stage["label"]
            stage_url = stage["url"]
            stage_keywords = stage.get("keywords_for_filter") or LinkedInQueryBuilder.extract_core_keywords(query_text)

            if stage_idx > 0:
                p_delay = round(random.uniform(2.5, 4.2), 1)
                self.log(f"\n🔄 Pivoting to search variation ({stage_idx+1}/{len(cascade)}): '{stage_label}' (pause {p_delay}s)...")
                if self._interruptible_sleep(p_delay, should_stop):
                    break

            self.log(f"🔍 Navigating to: {stage_label} ({stage_url})")
            if not self._goto(page, stage_url, stage_label):
                continue

            if self._interruptible_sleep(page_load_wait, should_stop):
                break

            scroll_attempts = 0
            consecutive_empty_scrolls = 0
            consecutive_dupes = 0
            stage_initial_count = len(posts_found)
            stage_evaluated_fingerprints = set()

            self.log(f"📜 Scanning feed for matching hiring posts (Target: {limit} unique, current: {len(posts_found)})...")

            while len(posts_found) < limit and scroll_attempts < max_stage_scrolls:
                if should_stop and should_stop():
                    self.log("🛑 Stop requested — ending feed scan.")
                    break
                if total_scrolls >= max_global_scrolls:
                    self.log(f"🛡️ Global scroll safety ceiling reached ({total_scrolls}/{max_global_scrolls}).")
                    break
                if (time.time() - session_start_time) >= max_session_duration:
                    self.log("🛡️ Session duration safety ceiling reached.")
                    break

                post_cards = page.query_selector_all(
                    "div[role='listitem'], "
                    ".feed-shared-update-v2, "
                    "div[data-urn*='urn:li:activity'], "
                    "div[data-view-name='search-entity-result-universal-template'], "
                    ".search-results-container .artdeco-card, "
                    "li.reusable-search__result-container, "
                    "div[data-view-name*='feed']"
                )

                card_matched_in_pass = False
                for card in post_cards:
                    if should_stop and should_stop():
                        break

                    parsed = JobParser.parse_post_card(
                        card,
                        target_keywords=stage_keywords,
                        domain_keywords=domain_keywords,
                        exclude_keywords=exclude_keywords,
                        max_yoe=max_yoe,
                        target_seniority=target_seniority
                    )
                    if not parsed:
                        continue

                    # Ensure verified direct post permalink
                    cur_link = parsed.get("link", "")
                    if not cur_link or ("/feed/update/" not in cur_link and "/posts/" not in cur_link and "lnkd.in/p/" not in cur_link):
                        direct_link = self._extract_post_permalink(card, page)
                        if direct_link:
                            parsed["link"] = direct_link
                            m_u = re.search(r'(urn:li:activity:\d+|activity-\d+)', direct_link)
                            if m_u:
                                parsed["job_id"] = m_u.group(1)

                    p_id = str(parsed.get("job_id") or "").strip()
                    c_link = str(parsed.get("link") or "").split("?")[0].rstrip("/")
                    author_title = (parsed.get("author_name") or parsed.get("title") or "").strip().lower()
                    desc_snip = (parsed.get("description") or "")[:80].strip().lower()
                    c_fingerprint = f"{author_title}::{desc_snip}"

                    # Skip cards already evaluated in this stage so they don't falsely increment duplicate count
                    if c_fingerprint in stage_evaluated_fingerprints:
                        continue
                    stage_evaluated_fingerprints.add(c_fingerprint)

                    # Cross-session & in-session deduplication check
                    is_dupe = False
                    if p_id and (p_id in session_seen_ids or p_id in existing_hashes):
                        is_dupe = True
                    elif c_link and c_link != "https://www.linkedin.com/feed" and c_link in existing_hashes:
                        is_dupe = True
                    elif c_fingerprint in existing_hashes:
                        is_dupe = True

                    if is_dupe:
                        consecutive_dupes += 1
                        continue

                    # Fresh unique post found!
                    consecutive_dupes = 0
                    consecutive_empty_scrolls = 0
                    card_matched_in_pass = True

                    if p_id:
                        session_seen_ids.add(p_id)
                        existing_hashes.add(p_id)
                    if c_link:
                        existing_hashes.add(c_link)
                    existing_hashes.add(c_fingerprint)

                    posts_found.append(parsed)
                    author = parsed.get("author_name", "Author")
                    preview = parsed.get("description", "")[:50].replace("\n", " ")
                    contact = f" [✉️ {parsed['contact_info']}]" if parsed.get("contact_info") else ""
                    post_ref = f" ({parsed['link']})" if "lnkd.in" in parsed.get("link", "") or "update" in parsed.get("link", "") else ""
                    self.log(f"  + [{len(posts_found)}/{limit}] {author}: {preview}...{contact}{post_ref}")

                    # Real-time SQLite commit — persist immediately so user never loses leads
                    try:
                        self.storage.save_jobs([parsed])
                        self.db.upsert_scraped_jobs([parsed])
                    except Exception as e:
                        pass

                    if progress_callback:
                        progress_callback(len(posts_found), limit, f"Collected {len(posts_found)}/{limit} unique posts")

                    HumanActions.reading_pause(text_len=len(parsed.get("description", "")), min_seconds=1.2, max_seconds=2.8)

                    if len(posts_found) >= limit:
                        break

                if not card_matched_in_pass:
                    consecutive_empty_scrolls += 1
                else:
                    consecutive_empty_scrolls = 0

                # Check if this feed has exhausted or is returning only repeats
                # Higher tolerance (10 empty scrolls or 35 consecutive dupes) prevents premature exit
                if consecutive_empty_scrolls >= 10 or consecutive_dupes >= 35:
                    reason = f"feed reached end ({consecutive_empty_scrolls} passes with no new items)" if consecutive_empty_scrolls >= 10 else f"high duplicate ratio ({consecutive_dupes} repeats)"
                    self.log(f"⚠️ Feed saturated on '{stage_label}' ({reason}). Yield from this stage: {len(posts_found) - stage_initial_count}. Advancing cascade...")
                    break

                # If 3 or more consecutive empty scrolls, trigger an active scroll nudge
                if consecutive_empty_scrolls >= 3:
                    try:
                        page.mouse.wheel(0, 800)
                        page.wait_for_timeout(300)
                        page.mouse.wheel(0, -150)
                    except Exception:
                        pass

                # Check and click genuine LinkedIn pagination buttons
                pagination_selectors = [
                    "button.scaffold-finite-scroll__load-button",
                    "button[aria-label*='See more results']",
                    "button[aria-label*='Show more results']",
                    "button.artdeco-button--muted:has-text('Show more results')",
                    "button.artdeco-button--secondary:has-text('Show more results')",
                    "button:has-text('Show more results')",
                    "button:has-text('See more results')",
                    "button:has-text('Load more')"
                ]
                for p_sel in pagination_selectors:
                    try:
                        btn = page.query_selector(p_sel)
                        if btn and btn.is_visible():
                            self.log("  🔘 Triggered LinkedIn pagination: clicking 'Show more results'...")
                            btn.click(timeout=1500)
                            self._interruptible_sleep(1.8, should_stop)
                            break
                    except Exception:
                        pass

                # Scroll smoothly with human-like steps
                HumanActions.human_scroll(page, min_steps=3, max_steps=6)
                scroll_attempts += 1
                total_scrolls += 1

                if scroll_attempts % 5 == 0:
                    self.log(f"📜 Scanning... {len(posts_found)}/{limit} unique leads found across cascade (pass {scroll_attempts}/{max_stage_scrolls})")

                if self._interruptible_sleep(scroll_delay + random.uniform(0.3, 1.2), should_stop):
                    break

        return posts_found

    def search_jobs(self, page, keywords: str, location: str = "", limit: int = 20, progress_callback: Optional[Callable[[int, int, str], None]] = None, should_stop: Optional[Callable[[], bool]] = None) -> List[Dict[str, Any]]:
        """
        Searches the standard LinkedIn Jobs board (/jobs/search).
        Scrolls through the job card list and extracts job details.
        """
        if keywords.startswith("http://") or keywords.startswith("https://"):
            jobs_url = keywords
        else:
            encoded_keywords = urllib.parse.quote(keywords)
            encoded_location = urllib.parse.quote(location)
            jobs_url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_keywords}&location={encoded_location}"

        self.log(f"🔍 Navigating to Jobs search: {jobs_url}")
        if not self._goto(page, jobs_url, "Jobs search"):
            return []

        page_load_wait = int(os.getenv("PAGE_LOAD_WAIT_MS", 5000)) / 1000
        if self._interruptible_sleep(page_load_wait, should_stop):
            return []

        jobs_found: List[Dict[str, Any]] = []
        seen_ids = set()
        scroll_attempts = 0
        max_scroll_attempts = int(os.getenv("MAX_SCROLL_ATTEMPTS", 60))
        scroll_delay = int(os.getenv("SCROLL_DELAY_MS", 3000)) / 1000

        self.log(f"📜 Scanning jobs board (target: {limit})...")

        while len(jobs_found) < limit and scroll_attempts < max_scroll_attempts:
            if should_stop and should_stop():
                self.log("🛑 Stop requested — ending jobs collection.")
                break

            job_cards = page.query_selector_all("li.jobs-search-results__list-item, div.job-card-container")
            for card in job_cards:
                if should_stop and should_stop():
                    break
                job_data = JobParser.parse_job_card(card)
                if job_data and job_data["job_id"] not in seen_ids:
                    seen_ids.add(job_data["job_id"])
                    jobs_found.append(job_data)
                    self.log(f"  + [{len(jobs_found)}/{limit}] {job_data['title']} at {job_data['company']}")

                    if progress_callback:
                        progress_callback(len(jobs_found), limit, f"Collected {len(jobs_found)} jobs")

                    if len(jobs_found) >= limit:
                        break

            # Scroll down the left job listing pane
            try:
                jobs_pane = page.query_selector(".jobs-search-results-list")
                if jobs_pane:
                    jobs_pane.evaluate("el => el.scrollBy(0, 600)")
                else:
                    HumanActions.smooth_scroll(page, scroll_steps=5)
            except Exception:
                HumanActions.smooth_scroll(page, scroll_steps=5)

            scroll_attempts += 1
            if scroll_attempts == 5 and not jobs_found:
                self.log("⚠️ No job cards matched yet — page may still be loading or selectors changed.")
            if scroll_attempts % 5 == 0:
                self.log(f"📜 Scanning... {len(jobs_found)}/{limit} collected (pass {scroll_attempts}/{max_scroll_attempts})")
            if self._interruptible_sleep(scroll_delay, should_stop):
                break

        return jobs_found

    def run(self, mode: str = "posts", keywords: str = "hiring product designer", location: str = "Remote", limit: int = 15,
            progress_callback: Optional[Callable[[int, int, str], None]] = None,
            should_stop: Optional[Callable[[], bool]] = None,
            domain_keywords: Optional[List[str]] = None,
            exclude_keywords: Optional[List[str]] = None,
            max_yoe: Optional[int] = None,
            target_seniority: Optional[str] = None,
            target_roles: Optional[List[str]] = None) -> int:
        self.log(f"\n🚀 Launching visible browser for LinkedIn {mode.upper()} scrape...")
        browser = self.manager.start()
        page = self.manager.new_page()

        try:
            if should_stop and should_stop():
                self.log("🛑 Stop requested before start — aborting scrape.")
                return 0
            if not self.ensure_logged_in(page, should_stop=should_stop):
                if should_stop and should_stop():
                    self.log("🛑 Scrape stopped by user.")
                else:
                    self.log("❌ Could not verify login. Aborting scrape.")
                return 0

            if mode == "posts":
                items = self.search_posts(
                    page, query_text=keywords, location=location, limit=limit,
                    progress_callback=progress_callback, should_stop=should_stop,
                    domain_keywords=domain_keywords, exclude_keywords=exclude_keywords,
                    max_yoe=max_yoe, target_seniority=target_seniority,
                    target_roles=target_roles
                )
            else:
                items = self.search_jobs(page, keywords=keywords, location=location, limit=limit, progress_callback=progress_callback, should_stop=should_stop)

            self.log(f"\n💾 Ensuring all {len(items)} items are committed to local database...")
            self.storage.save_jobs(items)
            added_count = self.db.upsert_scraped_jobs(items)
            self.log(f"✅ Finished! {len(items)} unique leads gathered ({added_count} new entries committed).")
            return len(items)

        except Exception as e:
            self.log(f"❌ Error during scrape: {e}")
            return 0
        finally:
            self.log("🛑 Closing browser...")
            self.manager.stop()
