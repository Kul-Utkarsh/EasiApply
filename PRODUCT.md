# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Non-technical job seekers looking for roles in tech/design rather than developers; they want automated discovery and outreach but need guided, plain-language onboarding rather than raw API keys and SMTP settings. They value hands-off automation while maintaining full local control over their personal data.

## Product Purpose
An autonomous desktop cockpit that scrapes LinkedIn hiring posts and jobs, scores each one against a locally parsed resume, and drafts tailored recruiter outreach so the user applies to the right roles faster with minimal manual hunting.

## Positioning
Outreach is part of the core discovery loop, not a separate tool — discovery → score → draft → send. Operates locally on-device for total privacy, distinguishing it from multi-tenant cloud application trackers.

## Operating Context
The application runs as a local single-user Python/FastAPI service on a Windows desktop, launched via a `.bat` file. Scraping relies on a visible Playwright Chrome session where the user might initially need to log into LinkedIn manually. The interface is viewed primarily on desktop monitors in a single browser tab.

## Capabilities and Constraints
- Scrapes both LinkedIn hiring posts (`//results/content`) and standard jobs (`/jobs/search`).
- Resumes (PDF/DOCX/TXT) are ingested and parsed locally using `pypdf`/`python-docx`, matching skills against a keyword taxonomy without AI sending personal text off-device.
- Match scoring uses a user-configured OpenAI-compatible AI gateway.
- Generates outbound email drafts with token insertion, meant for SMTP relay.
- Constraints: Local-first single-user SQLite (`data/applications.db`); file system resume store (`data/resumes/`); external dependency on bringing an AI gateway key and SMTP credentials. Selectors depend on LinkedIn's live DOM.

## Brand Commitments
The visual world is **Kinetic Neo-Tech Cockpit**. Designed to merge aerospace instrumentation with neo-brutalist tech precision. Dark-first, high contrast UI balancing deep obsidian substrates with electric neon lime accents. Zero fluff; an "Operate" mode tool focused on efficiency and technical clarity, deliberately avoiding generic SaaS dashboard templates.

## Evidence on Hand
The six core screens (Dashboard, Profile, Matches, Outreach, Analytics, Settings) are functionally built. The resume uploader successfully extracts local metadata. The Playwright scraper client exists. Activity streams are logged in a global ring buffer. There are no production case studies, live user metrics, or real testimonials yet—this is a working MVP with all fundamental systems wired.

## Product Principles
1. **Automate the funnel**: Discovery through to message drafting must be one seamless flow.
2. **Local privacy first**: Career markers, resumes, and embeddings never leave the device out-of-bounds.
3. **Cockpit over dashboard**: Density, legibility, and operational control prevail over decorative whitespace.
4. **Honest state**: Provide real-time telemetry on daemon activity; no theatrical fake loading spinners for processes that have failed.

## Accessibility & Inclusion
Must adhere to the Impeccable craft floor: support for 200% browser zoom, robust focus visibility without stripping outlines, full keyboard navigability across the six views, and adherence to system `prefers-reduced-motion` where practical, ensuring the high-contrast presentation remains legible (WCAG AA).