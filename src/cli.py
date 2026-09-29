"""
LinkedIn Job Automation Tool - Unified CLI Runner
"""
import os
import sys
from pathlib import Path
import argparse

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to path (cli.py lives in src/, so root is one level up)
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.scraper.client import LinkedInScraper
from src.storage.db import DatabaseManager
from src.ai.matcher import JobMatcher
from src.ai.draft_writer import DraftWriter
from src.utils.resume_manager import ResumeManager


def cmd_scrape(args):
    """Scrapes LinkedIn Posts or Job Board."""
    print(f"\n🚀 Scraping LinkedIn ({args.mode.upper()})...")
    print(f"   Keywords: {args.keywords}")
    print(f"   Limit:    {args.limit}")

    scraper = LinkedInScraper()
    count = scraper.run(
        mode=args.mode,
        keywords=args.keywords,
        location=args.location,
        limit=args.limit
    )
    print(f"\n🎉 Successfully saved {count} listings!")


def cmd_ai_match(args):
    """Runs AI Match analysis on unscored jobs."""
    print("\n🤖 Running Claude AI Match Analysis...")
    db = DatabaseManager()
    resume_mgr = ResumeManager()
    active_res = resume_mgr.list_resumes()[0] if resume_mgr.list_resumes() else "base_resume.md"
    resume_text = resume_mgr.get_resume_text(active_res)

    matcher = JobMatcher(base_resume_text=resume_text)
    apps = [a for a in db.get_all_applications() if a.match_score == 0.0 or a.status == "Scraped"]

    for a in apps:
        print(f"   -> Analyzing: {a.company} — {a.title}")
        res = matcher.analyze_match(a.title, a.company, a.description or "")
        if res:
            db.update_application(a.id, match_score=res.match_score, match_reason=res.reasoning, status="Scored")
            print(f"      Score: {res.match_score:.0f}%")
    print("\n✅ AI Matching Complete!")


def cmd_draft(args):
    """Generates email drafts for top matches."""
    print("\n✉️ Generating Email Drafts for top matches...")
    db = DatabaseManager()
    resume_mgr = ResumeManager()
    active_res = resume_mgr.list_resumes()[0] if resume_mgr.list_resumes() else "base_resume.md"
    resume_text = resume_mgr.get_resume_text(active_res)

    writer = DraftWriter(base_resume_text=resume_text)
    apps = [a for a in db.get_all_applications() if (a.match_score or 0) >= 70.0 and not a.email_draft_body]

    for a in apps:
        print(f"   -> Drafting email for: {a.company}")
        res = writer.generate_application_draft(
            job_title=a.title,
            job_company=a.company,
            job_description=a.description or "",
            recipient_name=a.author_name or "Hiring Manager",
            match_score=a.match_score,
            match_reasoning=a.match_reason or ""
        )
        if res:
            em, rt = res
            db.update_application(
                a.id,
                email_draft_subject=em.subject,
                email_draft_body=em.body,
                tailored_resume_text=rt.tailored_sections,
                status="Tailored"
            )
    print("\n✅ Email Drafts Generated!")


def cmd_server(args):
    """Starts the EasiApply FastAPI cockpit web server."""
    print("\n🌐 Launching EasiApply Cockpit at http://127.0.0.1:8000 ...")
    os.system("python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000")


def cmd_full(args):
    """Runs the complete flow: scrape -> match -> draft."""
    cmd_scrape(args)
    cmd_ai_match(args)
    cmd_draft(args)
    print("\n✅ Full pipeline completed successfully!")

def main():
    parser = argparse.ArgumentParser(description="LinkedIn Job Automation CLI")
    subparsers = parser.add_subparsers(dest="command")

    # Scrape
    sc = subparsers.add_parser("scrape", help="Scrape LinkedIn")
    sc.add_argument("--mode", choices=["posts", "jobs"], default="posts", help="Search feed posts or jobs board")
    sc.add_argument("--keywords", "-k", default="hiring product designer", help="Search query")
    sc.add_argument("--location", "-l", default="Remote", help="Location (for jobs board)")
    sc.add_argument("--limit", "-n", type=int, default=15, help="Number of items")

    # Match
    subparsers.add_parser("match", help="Run AI scoring on unscored items")

    # Draft
    subparsers.add_parser("draft", help="Generate drafts for top matches")

    # Full Pipeline
    fp = subparsers.add_parser("full", help="Run scrape, then match, then draft")
    fp.add_argument("--mode", choices=["posts", "jobs"], default="posts", help="Search feed posts or jobs board")
    fp.add_argument("--keywords", "-k", default="hiring product designer", help="Search query")
    fp.add_argument("--location", "-l", default="Remote", help="Location (for jobs board)")
    fp.add_argument("--limit", "-n", type=int, default=15, help="Number of items")

    # Server
    subparsers.add_parser("server", help="Launch web dashboard")

    args = parser.parse_args()

    if args.command == "scrape":
        cmd_scrape(args)
    elif args.command == "match":
        cmd_ai_match(args)
    elif args.command == "draft":
        cmd_draft(args)
    elif args.command == "full":
        cmd_full(args)
    elif args.command == "server":
        cmd_server(args)
    else:
        # Default action: launch dashboard
        cmd_server(args)


if __name__ == "__main__":
    main()
