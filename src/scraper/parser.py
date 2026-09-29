import re
from typing import Dict, Any, Optional, List


class JobParser:
    """
    Extracts structured data from LinkedIn Job Cards and LinkedIn Feed Posts.
    """

    @staticmethod
    def extract_emails(text: str) -> list:
        """Find any email addresses mentioned in a text block."""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        return list(set(re.findall(email_pattern, text, re.IGNORECASE)))

    @staticmethod
    def parse_job_card(card_element) -> Dict[str, Any]:
        """
        Parses a standard LinkedIn Job Listing card from the Jobs search results.
        Tries multiple modern CSS selector fallbacks.
        """
        job_data = {
            "title": "Unknown Title",
            "company": "Unknown Company",
            "location": "Unknown Location",
            "link": "",
            "job_id": "",
            "source_type": "jobs",
            "contact_info": "",
            "author_name": "",
            "description": ""
        }

        try:
            # Title & Link - multiple selector fallbacks for modern LinkedIn
            title_selectors = [
                "a.job-card-list__title",
                "a.job-card-container__link",
                "a[data-control-name='job_card_title']",
                ".job-card-list__title",
                "a[href*='/jobs/view/']"
            ]
            for sel in title_selectors:
                el = card_element.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if text:
                        job_data["title"] = text
                    href = el.get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            href = f"https://www.linkedin.com{href}"
                        # Strip query params to get clean job link
                        clean_link = href.split("?")[0]
                        job_data["link"] = clean_link
                        match = re.search(r'/view/(\d+)', clean_link)
                        if match:
                            job_data["job_id"] = match.group(1)
                    if job_data["title"] != "Unknown Title":
                        break

            # Company name fallbacks
            comp_selectors = [
                ".job-card-container__primary-description",
                ".job-card-container__company-name",
                ".artdeco-entity-lockup__subtitle",
                "span.job-card-container__primary-description"
            ]
            for sel in comp_selectors:
                el = card_element.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if text:
                        job_data["company"] = text
                        break

            # Location fallbacks
            loc_selectors = [
                ".job-card-container__metadata-item",
                ".artdeco-entity-lockup__caption",
                ".job-card-container__metadata-wrapper"
            ]
            for sel in loc_selectors:
                el = card_element.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if text:
                        job_data["location"] = text.split("\n")[0].strip()
                        break

        except Exception as e:
            print(f"⚠️ Warning parsing job card: {e}")

        return job_data

    @staticmethod
    def extract_yoe_from_text(text: str) -> Optional[int]:
        """Extract minimum years of experience required from post text."""
        if not text:
            return None
        low = text.lower()
        candidates = []
        # 1. Range or explicit years: e.g. "5+ years", "10+ yrs", "3-5 years", "min 2 years"
        m_range = re.findall(r'(\d{1,2})\s*(?:[-–—to]+|\+)?\s*(?:(\d{1,2})\+?)?\s*(?:years?|yrs?)(?:\s+(?:of\s+)?experience|\s+in\b|\s+required|\s+relevant)?', low)
        for m in m_range:
            y1 = int(m[0]) if m[0] else None
            y2 = int(m[1]) if len(m) > 1 and m[1] else None
            if y1 and 0 < y1 <= 25:
                candidates.append(y1)
            if y2 and 0 < y2 <= 25:
                candidates.append(y2)

        # 2. "minimum of X years", "at least X yrs"
        m_min = re.findall(r'(?:minimum|min\.?|at least)\s*(?:of\s*)?(\d{1,2})\s*(?:years?|yrs?)', low)
        for val in m_min:
            n = int(val)
            if 0 < n <= 25:
                candidates.append(n)

        # 3. "X+ years of"
        m_plus = re.findall(r'(\d{1,2})\+\s*(?:years?|yrs?)', low)
        for val in m_plus:
            n = int(val)
            if 0 < n <= 25:
                candidates.append(n)

        # 4. Word numbers: "five+ years", "at least three years"
        word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        for w, num in word_map.items():
            if re.search(r'\b(?:at least|min(?:imum)?|requires?|with)\s+' + w + r'\s*(?:\+)?\s*(?:years?|yrs?)', low):
                candidates.append(num)

        return min(candidates) if candidates else None

    @staticmethod
    def extract_seniority_from_title_and_text(title: str, text: str = "") -> str:
        """Categorize seniority from title and post header."""
        comb = f"{title} {text[:300]}".lower()
        if re.search(r'\b(?:director|vp|vice president|head of|chief|c-level|executive)\b', comb):
            return "Director / Executive"
        if re.search(r'\b(?:principal|staff|architect)\b', comb):
            return "Staff / Principal"
        if re.search(r'\b(?:lead|manager)\b', comb):
            return "Lead"
        if re.search(r'\b(?:senior|sr\.?)\b', comb):
            return "Senior"
        if re.search(r'\b(?:junior|jr\.?|associate|entry|intern|graduate)\b', comb):
            return "Junior / Entry"
        return "Mid-Level"

    @staticmethod
    def check_domain_and_yoe_fit(
        post_title: str,
        post_text: str,
        domain_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        max_yoe: Optional[int] = None,
        target_seniority: Optional[str] = None,
        target_locations: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """Verify if a post aligns with candidate's domain, seniority, YOE, and location."""
        lower_title = post_title.lower()
        lower_text = post_text.lower()

        # 1. Negative Exclude Keywords Gate
        if exclude_keywords:
            for ex in exclude_keywords:
                ex_clean = ex.strip().lower()
                if ex_clean and re.search(r'\b' + re.escape(ex_clean) + r'\b', lower_text):
                    # Check if candidate domain keywords outweigh/reconcile it
                    has_domain_overlap = False
                    if domain_keywords:
                        has_domain_overlap = any(
                            re.search(r'\b' + re.escape(dk.lower()) + r'\b', lower_text)
                            for dk in domain_keywords if len(dk) > 2
                        )
                    if not has_domain_overlap:
                        return False, f"Domain mismatch (contains excluded term '{ex}')"

        # 2. Required Experience Gate
        req_yoe = JobParser.extract_yoe_from_text(post_text)
        if req_yoe is not None and max_yoe is not None and max_yoe > 0:
            if req_yoe > max_yoe:
                return False, f"YOE mismatch (post requires {req_yoe}+ YOE, exceeds max target {max_yoe} YOE)"

        # 3. Seniority Fit Gate (Multi-tier: Junior, Mid, Senior)
        is_junior_target = False
        is_mid_target = False
        is_senior_target = False

        if target_seniority:
            ts_low = target_seniority.lower()
            if any(k in ts_low for k in ["junior", "entry", "associate", "1–2", "0-2", "1-2"]):
                is_junior_target = True
            elif any(k in ts_low for k in ["mid", "3–5", "3-5"]):
                is_mid_target = True
            elif any(k in ts_low for k in ["senior", "5+"]):
                is_senior_target = True
        elif max_yoe is not None:
            if max_yoe <= 2:
                is_junior_target = True
            elif max_yoe <= 5:
                is_mid_target = True

        # Header context to check for seniority keywords (title + first 400 chars of post text)
        role_context = f"{lower_title} {lower_text[:400]}"

        if is_junior_target:
            disqualified_junior = [
                "director", "vp", "vice president", "head of", "principal", "staff", "chief",
                "lead", "senior", "sr.", "sr ", "manager", "managing"
            ]
            for dt in disqualified_junior:
                if re.search(r'\b' + re.escape(dt) + r'\b', role_context):
                    return False, f"Seniority mismatch (post requires '{dt.title()}', exceeds target Junior/Entry level)"

        elif is_mid_target:
            disqualified_mid = [
                "director", "vp", "vice president", "head of", "principal", "staff", "chief", "lead"
            ]
            for dt in disqualified_mid:
                if re.search(r'\b' + re.escape(dt) + r'\b', role_context):
                    return False, f"Seniority mismatch (post requires '{dt.title()}', exceeds target Mid-Level)"

        elif is_senior_target:
            disqualified_senior = ["director", "vp", "vice president", "head of", "chief"]
            for dt in disqualified_senior:
                if re.search(r'\b' + re.escape(dt) + r'\b', role_context):
                    return False, f"Seniority mismatch (post requires '{dt.title()}', exceeds target Senior level)"

        # 4. Strict Location / Remote Conflict Gate
        if target_locations:
            clean_targets = [loc.strip().lower() for loc in target_locations if loc.strip()]
            wants_remote_only = any("remote" in t for t in clean_targets) and not any("hybrid" in t or "on-site" in t or "onsite" in t for t in clean_targets)
            if wants_remote_only:
                strict_onsite = re.search(r'\b(?:strictly\s+on-?site|mandatory\s+(?:in-?office|on-?site)|no\s+remote|not\s+remote|100%\s+(?:on-?site|in-?office)|in-?person\s+only)\b', lower_text)
                if strict_onsite:
                    return False, "Location mismatch (post requires mandatory in-person/on-site, target is Remote)"

        return True, "OK"

    @staticmethod
    def parse_post_card(
        post_element,
        target_keywords: Optional[List[str]] = None,
        domain_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        max_yoe: Optional[int] = None,
        target_seniority: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Parses a post from LinkedIn Universal Search -> Posts section.
        Extracts author, company/headline, full post text, contact emails,
        and enforces domain and YOE relevance aligned with the candidate.
        """
        post_data = {
            "title": "Hiring Post",
            "company": "LinkedIn Member",
            "location": "Remote / See Post",
            "link": "",
            "job_id": "",
            "source_type": "posts",
            "contact_info": "",
            "author_name": "LinkedIn User",
            "author_profile_url": "",
            "description": ""
        }

        try:
            # 1. Author Name (+ profile link when the actor name is a link)
            author_selectors = [
                ".update-components-actor__name",
                ".update-components-actor__title",
                "span.update-components-actor__name span[aria-hidden='true']",
                ".feed-shared-actor__name"
            ]
            for sel in author_selectors:
                el = post_element.query_selector(sel)
                if el:
                    name = el.inner_text().strip()
                    if name:
                        post_data["author_name"] = name
                        post_data["company"] = name
                        break

            # 1b. Author profile URL — actor meta links point at /in/<slug>
            for sel in [
                "a.update-components-actor__meta-link",
                ".update-components-actor__meta a[href*='/in/']",
                "a[href*='linkedin.com/in/']",
            ]:
                try:
                    a_el = post_element.query_selector(sel)
                except Exception:
                    a_el = None
                if a_el:
                    href = (a_el.get_attribute("href") or "").strip()
                    if href and "/in/" in href:
                        if href.startswith("/"):
                            href = f"https://www.linkedin.com{href}"
                        post_data["author_profile_url"] = href.split("?")[0]
                        break

            # 2. Author Headline / Subtitle (often contains company/role)
            sub_selectors = [
                ".update-components-actor__description",
                ".feed-shared-actor__description",
                ".update-components-actor__supplementary-actor-info"
            ]
            for sel in sub_selectors:
                el = post_element.query_selector(sel)
                if el:
                    desc = el.inner_text().strip()
                    if desc:
                        post_data["company"] = f"{post_data['author_name']} ({desc[:60]}...)"
                        break

            # 3. Post Text (The JD / Hiring message)
            text_selectors = [
                ".update-components-text",
                ".feed-shared-update-v2__description",
                ".feed-shared-text",
                ".feed-shared-inline-show-more-text"
            ]
            full_text = ""
            for sel in text_selectors:
                el = post_element.query_selector(sel)
                if el:
                    # Check if there is a '...see more' button inside and click it to get full text
                    see_more = el.query_selector("button.feed-shared-inline-show-more-text__see-more-less-toggle, button[aria-label*='see more']")
                    if see_more:
                        try:
                            see_more.click(timeout=1000)
                        except Exception:
                            pass
                    full_text = el.inner_text().strip()
                    if full_text:
                        break

            # Fallback for modern LinkedIn layout with obfuscated class names
            if not full_text:
                raw_text = (post_element.inner_text() or "").strip()
                if len(raw_text) >= 30:
                    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
                    if lines and lines[0].lower() == "feed post":
                        lines = lines[1:]
                    if lines:
                        if post_data["author_name"] == "LinkedIn User":
                            post_data["author_name"] = lines[0]
                            post_data["company"] = lines[0]
                        full_text = "\n".join(lines)

            post_data["description"] = full_text

            # If the post doesn't have enough text, skip it (likely an image/poll only)
            if len(full_text) < 30:
                return None

            # 4. Extract any emails from the post text
            emails = JobParser.extract_emails(full_text)
            if emails:
                post_data["contact_info"] = ", ".join(emails)

            # 4b. Disqualify candidate / job-seeker posts (#OpenToWork, looking for role, hire me)
            lower_text = full_text.lower()
            candidate_signals = [
                "#opentowork", "open to work", "open for opportunities", "open for new opportunities",
                "looking for my next", "seeking a new", "seeking new opportunities", "seeking opportunities",
                "actively seeking", "laid off", "recently laid off", "unemployed", "looking for a job",
                "hire me", "my resume is attached", "reach out if you have any leads", "looking for roles",
                "seeking entry level", "seeking internship", "open to roles", "available for hire"
            ]
            if any(cand in lower_text for cand in candidate_signals):
                return None

            # 4c. Disqualify career milestones / courses / celebratory announcements
            milestone_signals = [
                "pleased to share that i started", "excited to share that i joined",
                "thrilled to announce that i started", "happy to share that i'm starting a new position",
                "i'm happy to share that i'm starting a new position", "i have joined", "joined as a",
                "completed the course", "certificate of completion", "bootcamp graduate"
            ]
            if any(ms in lower_text for ms in milestone_signals):
                return None

            # 4d. Hiring relevance check: verify genuine employer/recruiter hiring intent
            hiring_signals = [
                "we're hiring", "we are hiring", "i'm hiring", "i am hiring", "team is hiring",
                "our team is growing", "looking to hire", "hiring for", "job opening", "job vacancy",
                "vacancies", "position available", "send cv", "send resume", "email your cv",
                "email your resume", "share your resume", "dm your resume", "reach out with your cv",
                "apply at", "apply here", "apply via", "join our team", "looking for a talented",
                "looking for an experienced", "join us as", "hiring a"
            ]
            has_hiring_signal = any(sig in lower_text for sig in hiring_signals)
            has_contact_signal = bool(emails or "@" in lower_text or "mailto:" in lower_text)

            if not has_hiring_signal and not has_contact_signal:
                return None

            # 4e. Target Keyword Gate: verify the post mentions at least one of the targeted terms
            if target_keywords:
                matched_kw = any(kw in lower_text or kw in post_data["company"].lower() for kw in target_keywords)
                if not matched_kw:
                    return None

            # 4f. Smart Location Detection from post text
            loc_match = re.search(r'(?i)(?:location|based in|workplace|mode)\s*[:\-–]?\s*([A-Za-z0-9\s,\-\/]{3,35})', full_text)
            if loc_match:
                cand_loc = loc_match.group(1).split("\n")[0].strip()
                if cand_loc and len(cand_loc) < 35:
                    post_data["location"] = cand_loc
            elif "remote" in lower_text:
                post_data["location"] = "Remote"
            elif "hybrid" in lower_text:
                post_data["location"] = "Hybrid"
            elif "on-site" in lower_text or "onsite" in lower_text:
                post_data["location"] = "On-site"
            else:
                post_data["location"] = "Location not specified in post"

            # Fallback for author profile/company link
            if not post_data.get("author_profile_url"):
                try:
                    for a in post_element.query_selector_all("a[href*='/in/'], a[href*='/company/']"):
                        href = (a.get_attribute("href") or "").split("?")[0]
                        if href:
                            post_data["author_profile_url"] = href
                            break
                except Exception:
                    pass

            # 5. Extract a sensible title from explicit role labels, target keywords, or post text
            # CRITICAL: Never allow the author/recruiter name, company name, or generic header junk to become the title.
            title_found = ""
            author_val = (post_data.get("author_name") or "").strip()
            author_val_lower = author_val.lower()

            # Clean full text for title extraction by removing top author/connection header lines
            raw_lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
            content_lines = []
            for ln in raw_lines:
                ln_low = ln.lower()
                if author_val_lower and author_val_lower in ln_low:
                    continue
                if re.match(r'^(•\s*)?\d+(st|nd|rd|th)\+?$', ln_low):
                    continue
                if re.match(r'^\d+[smhdwy]\b', ln_low) or '• edited' in ln_low or ln_low in ['follow', 'feed post', 'see more', '… more', 'view more', 'hi all,', 'hello everyone,']:
                    continue
                content_lines.append(ln)

            cleaned_content_text = "\n".join(content_lines)

            # A. Check for explicit role label lines: "Role: Senior Product Designer", "Position: UI/UX Designer"
            label_match = re.search(r'(?i)(?:role|position|job title|hiring for|looking for(?:\s+a|\s+an)?|we are hiring(?:\s*[:\-–]?\s*|\s+for\s+)|we’re hiring(?:\s*[:\-–]?\s*|\s+for\s+))\s*[:\-–]?\s*([A-Za-z0-9\s/&,–-]{3,60})', cleaned_content_text)
            if label_match:
                cand_title = label_match.group(1).split("\n")[0].strip()
                cand_title = re.sub(r'^[–\-:\s]+', '', cand_title).strip()
                if cand_title and len(cand_title) >= 3 and not any(w in cand_title.lower() for w in ['multiple', 'fresher', 'immediate', 'http', 'anyone']):
                    if cand_title.lower() != author_val_lower:
                        title_found = cand_title

            # B. Check early content lines for common role keywords or target keywords
            if not title_found:
                role_keywords = ["designer", "developer", "engineer", "manager", "lead", "architect", "intern", "specialist", "product", "analyst", "consultant", "tester", "ui/ux", "ux/ui"]
                all_role_keys = set(role_keywords)
                if target_keywords:
                    all_role_keys.update([k.lower() for k in target_keywords])

                for ln in content_lines[:12]:
                    clean_ln = ln.strip()
                    # Strip common prefixes like emojis, bullets, numbers, "We are hiring"
                    clean_ln = re.sub(r'(?i)^(🚀|🚨|📢|🔥|we\s*are\s*hiring\s*[:\-–]?\s*|we’re\s*hiring\s*[:\-–]?\s*|urgent\s*hiring\s*[:\-–]?\s*|hiring\s*[:\-–]?\s*|open\s*positions?\s*[:\-–]?\s*|📌\s*open\s*positions?\s*[:\-–]?\s*)', '', clean_ln).strip()
                    clean_ln = re.sub(r'^[0-9]+[\.\)]\s*', '', clean_ln).strip()
                    clean_ln = re.sub(r'^[•\-\*🎨💠👉]\s*', '', clean_ln).strip()

                    if any(k in clean_ln.lower() for k in all_role_keys) and 3 < len(clean_ln) < 70:
                        if clean_ln.lower() != author_val_lower:
                            title_found = clean_ln
                            break

            # C. Fallback: use target_keywords or first clean content line (never author name!)
            if not title_found:
                if target_keywords:
                    # Choose a clean representative target role (e.g., "UI/UX Designer")
                    title_found = target_keywords[0].title()
                elif content_lines:
                    first_clean = content_lines[0][:80].strip()
                    if first_clean.lower() != author_val_lower and len(first_clean) >= 3:
                        title_found = first_clean
                    else:
                        title_found = "Hiring Opportunity"
                else:
                    title_found = "Hiring Opportunity"

            post_data["title"] = title_found

            # Domain & Experience Fit Check
            fit_ok, fit_reason = JobParser.check_domain_and_yoe_fit(
                post_title=title_found,
                post_text=full_text,
                domain_keywords=domain_keywords,
                exclude_keywords=exclude_keywords,
                max_yoe=max_yoe,
                target_seniority=target_seniority
            )
            if not fit_ok:
                print(f"⚠️ Filtered post: {fit_reason}")
                return None

            # 6. Post Link or unique ID - prioritize direct permalinks
            direct_post_link = ""
            import urllib.parse

            # A. Scan all anchors inside the card for permalinks or URN query params
            try:
                for a_tag in post_element.query_selector_all("a[href]"):
                    href = (a_tag.get_attribute("href") or "").strip()
                    if not href:
                        continue
                    unquoted = urllib.parse.unquote(href)

                    # Check for highlightedUpdateUrn or activity URN anywhere in URL/params
                    m_urn = re.search(r'urn:li:activity:(\d+)', unquoted)
                    if m_urn:
                        direct_post_link = f"https://www.linkedin.com/feed/update/urn:li:activity:{m_urn.group(1)}/"
                        post_data["job_id"] = f"urn:li:activity:{m_urn.group(1)}"
                        break

                    # Check for direct /feed/update/ or standalone /posts/ URLs (exclude /in/ profile paths)
                    if "/feed/update/" in href or ("/posts/" in href and "/in/" not in href):
                        if href.startswith("/"):
                            href = f"https://www.linkedin.com{href}"
                        m_act = re.search(r'activity:(\d+)|activity-(\d+)', href)
                        if m_act:
                            act_id = m_act.group(1) or m_act.group(2)
                            direct_post_link = f"https://www.linkedin.com/feed/update/urn:li:activity:{act_id}/"
                            post_data["job_id"] = f"urn:li:activity:{act_id}"
                            break
                        if "/in/" not in href:
                            direct_post_link = href.split("?")[0]
                            break
                    elif "/in/" in href and not post_data.get("author_profile_url"):
                        post_data["author_profile_url"] = href.split("?")[0]
            except Exception:
                pass

            # B. Check data attributes on the card or descendant nodes
            if not direct_post_link:
                try:
                    urn_val = post_element.evaluate('''el => {
                        const target = el.querySelector('[data-urn*="activity"], [data-activity-urn], [data-ch-urn*="activity"], [data-id*="activity"]');
                        if (target) {
                            return target.getAttribute('data-urn') || target.getAttribute('data-activity-urn') || target.getAttribute('data-ch-urn') || target.getAttribute('data-id');
                        }
                        return el.getAttribute('data-urn') || el.getAttribute('data-id') || null;
                    }''')
                    if urn_val:
                        m_u = re.search(r'urn:li:activity:(\d+)', urn_val)
                        if m_u:
                            direct_post_link = f"https://www.linkedin.com/feed/update/urn:li:activity:{m_u.group(1)}/"
                            post_data["job_id"] = f"urn:li:activity:{m_u.group(1)}"
                except Exception:
                    pass

            # C. Interactive fallback: click card control menu -> "Copy link to post"
            # Scoped strictly to the card's open menu item
            if not direct_post_link:
                try:
                    copied_link = post_element.evaluate('''async (el) => {
                        const menuBtn = el.querySelector('button[aria-label*="control menu"], button[aria-label*="Open control menu"]');
                        if (!menuBtn) return null;
                        let copied = null;
                        const orig = navigator.clipboard ? navigator.clipboard.writeText : null;
                        if (navigator.clipboard) {
                            navigator.clipboard.writeText = async (t) => {
                                copied = t;
                                return Promise.resolve();
                            };
                        }
                        menuBtn.click();
                        await new Promise(r => setTimeout(r, 200));
                        // Scope to open dropdown inside or attached to document
                        const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
                        const copyItem = items.find(x => x.innerText && x.innerText.toLowerCase().includes('copy link to post'));
                        if (copyItem) {
                            copyItem.click();
                            for (let i = 0; i < 8; i++) {
                                if (copied) break;
                                await new Promise(r => setTimeout(r, 80));
                            }
                        } else {
                            // close menu if not found
                            menuBtn.click();
                        }
                        if (orig && navigator.clipboard) {
                            navigator.clipboard.writeText = orig;
                        }
                        return copied;
                    }''')
                    if copied_link and ("linkedin.com" in copied_link or "lnkd.in" in copied_link):
                        direct_post_link = copied_link.strip()
                        # If copied link contains activity ID, canonicalize it immediately
                        m_act = re.search(r'activity:(\d+)|activity-(\d+)', direct_post_link)
                        if m_act:
                            act_id = m_act.group(1) or m_act.group(2)
                            direct_post_link = f"https://www.linkedin.com/feed/update/urn:li:activity:{act_id}/"
                            post_data["job_id"] = f"urn:li:activity:{act_id}"
                except Exception:
                    pass

            # Discard direct_post_link if it accidentally resolved to a profile URL
            if direct_post_link and ("/in/" in direct_post_link and "/feed/update/" not in direct_post_link):
                if not post_data.get("author_profile_url"):
                    post_data["author_profile_url"] = direct_post_link
                direct_post_link = ""

            if direct_post_link:
                post_data["link"] = direct_post_link
            else:
                clean_q = f"{post_data.get('author_name', '')} {post_data.get('title', '')}".strip()
                post_data["link"] = f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(clean_q)}"

            if not post_data.get("job_id"):
                import hashlib
                hash_id = hashlib.md5(f"{post_data['author_name']}_{full_text[:40]}".encode()).hexdigest()[:12]
                post_data["job_id"] = f"post_{hash_id}"

            return post_data

        except Exception as e:
            print(f"⚠️ Warning parsing post: {e}")
            return None
