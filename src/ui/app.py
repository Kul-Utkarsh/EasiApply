import streamlit as st
import pandas as pd
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.storage.db import DatabaseManager
from src.utils.resume_manager import ResumeManager
from src.scraper.client import LinkedInScraper
from src.ai.matcher import JobMatcher
from src.ai.draft_writer import DraftWriter
from src.mail.smtp_client import EmailClient
from src.compiler.resume_compiler import ResumeCompiler

st.set_page_config(
    page_title="Job & Hiring Automation",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background-color: #FAFAFA;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.vercel-title {
    font-size: 1.75rem;
    font-weight: 700;
    color: #111111;
    letter-spacing: -0.02em;
    margin-bottom: 0.15rem;
    line-height: 1.3;
}
.vercel-subtitle {
    font-size: 0.9rem;
    color: #666666;
    font-weight: 400;
    margin-bottom: 1.5rem;
    line-height: 1.5;
}

/* Primary black buttons — force white text */
div.stButton > button[kind="primary"],
div.stButton > button[kind="secondary"],
div.stButton > button {
    background-color: #111111 !important;
    color: #FFFFFF !important;
    border: 1px solid #111111 !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    min-height: 40px;
}
div.stButton > button:hover {
    background-color: #333333 !important;
    border-color: #333333 !important;
    color: #FFFFFF !important;
}
div.stButton > button p,
div.stButton > button span {
    color: #FFFFFF !important;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #EAEAEA;
    border-radius: 8px;
    padding: 1rem 1.25rem;
}
div[data-testid="stMetricValue"] {
    font-size: 1.5rem !important;
    font-weight: 600 !important;
    color: #111111 !important;
}
div[data-testid="stMetricLabel"] {
    color: #666666 !important;
    font-size: 0.8rem !important;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #FFFFFF;
    border-right: 1px solid #EAEAEA;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 1px solid #EAEAEA;
}
.stTabs [data-baseweb="tab"] {
    padding: 8px 16px;
    font-weight: 500;
    color: #666666;
}
.stTabs [aria-selected="true"] {
    color: #111111 !important;
    border-bottom: 2px solid #111111 !important;
}

/* File uploader */
[data-testid="stFileUploader"] section {
    border: 1px dashed #CCCCCC;
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)


def main_dashboard():
    db = DatabaseManager()
    resume_mgr = ResumeManager()

    st.markdown('<div class="vercel-title">Job & Hiring Feed Automation</div>', unsafe_allow_html=True)
    st.markdown('<div class="vercel-subtitle">Discover hiring posts, score with AI, tailor resumes, and send applications.</div>', unsafe_allow_html=True)

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown("### Resume Manager")

        uploaded_files = st.file_uploader(
            "Upload Resume (PDF, DOCX, MD, TXT)",
            type=["pdf", "docx", "md", "txt"],
            accept_multiple_files=True
        )
        if uploaded_files:
            for uf in uploaded_files:
                resume_mgr.save_uploaded_file(uf)
            st.success(f"Uploaded {len(uploaded_files)} file(s)!")

        available_resumes = resume_mgr.list_resumes()
        if available_resumes:
            active_resume_file = st.selectbox(
                "Active Resume for AI Matching",
                available_resumes,
                index=0
            )
            active_resume_text = resume_mgr.get_resume_text(active_resume_file)
            with st.expander("Preview Active Resume", expanded=False):
                preview = active_resume_text[:2000]
                if len(active_resume_text) > 2000:
                    preview += "..."
                st.text_area("Resume Text", value=preview, height=180, disabled=True)
        else:
            active_resume_text = "No resume uploaded."

        st.divider()
        st.markdown("### Filters")
        search_filter = st.text_input("Search keywords / company")
        source_filter = st.selectbox("Source Type", ["All", "posts (LinkedIn Feed)", "jobs (Job Board)"])
        status_filter = st.selectbox("Status", ["All", "Scraped", "Scored", "Tailored", "Applied", "Interviewing", "Rejected"])
        min_score_filter = st.slider("Minimum Match Score (%)", 0, 100, 0)

        st.divider()
        st.caption("All data stays local in data/applications.db")

    # --- SCRAPER CONTROL ---
    st.markdown("#### Scraper Control")

    col_mode, col_kw, col_loc, col_limit, col_btn = st.columns([1.5, 2.5, 1.5, 1, 1.2])

    with col_mode:
        search_mode = st.radio(
            "Search Target",
            ["LinkedIn Posts", "LinkedIn Jobs"],
            help="Posts = recruiter/founder hiring posts. Jobs = formal job board."
        )

    with col_kw:
        default_kw = "hiring product designer" if search_mode == "LinkedIn Posts" else "Product Designer"
        keywords_input = st.text_input("Role / Keywords", value=default_kw)

    with col_loc:
        loc_input = st.text_input("Location", value="Remote", disabled=(search_mode == "LinkedIn Posts"))

    with col_limit:
        limit_input = st.number_input("Limit", min_value=5, max_value=50, value=15, step=5)

    with col_btn:
        st.write("")
        st.write("")
        start_scrape_btn = st.button("Start Scrape", use_container_width=True)

    if start_scrape_btn:
        st.info("Opening Chrome browser... Watch it scroll and collect posts on your screen.")
        log_box = st.empty()
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_log(msg):
            log_box.markdown(f"`{msg}`")

        def update_progress(current, total, msg):
            progress_bar.progress(min(current / max(total, 1), 1.0))
            status_text.text(msg)

        mode_key = "posts" if search_mode == "LinkedIn Posts" else "jobs"
        scraper = LinkedInScraper(log_callback=update_log)
        count = scraper.run(
            mode=mode_key,
            keywords=keywords_input,
            location=loc_input,
            limit=limit_input,
            progress_callback=update_progress
        )
        st.success(f"Scraping complete! Collected {count} new entries.")
        st.rerun()

    # --- METRICS & BATCH ACTIONS ---
    applications = db.get_all_applications()

    app_data = []
    for a in applications:
        app_data.append({
            "id": a.id,
            "title": a.title,
            "company": a.company,
            "location": a.location or "Remote",
            "source_type": a.source_type or "jobs",
            "status": a.status or "Scraped",
            "match_score": a.match_score or 0.0,
            "match_reason": a.match_reason or "Not evaluated yet",
            "link": a.link or "#",
            "contact_info": a.contact_info or "",
            "author_name": a.author_name or "",
            "description": a.description or "",
            "email_subject": a.email_draft_subject or "",
            "email_body": a.email_draft_body or "",
            "tailored_resume": a.tailored_resume_text or ""
        })

    df = pd.DataFrame(app_data)

    if not df.empty:
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Collected", len(df))
        m2.metric("LinkedIn Posts", len(df[df["source_type"] == "posts"]))
        m3.metric("Job Board", len(df[df["source_type"] == "jobs"]))
        m4.metric("High Matches (>75%)", len(df[df["match_score"] >= 75]))
        m5.metric("Applied", len(df[df["status"].isin(["Applied", "Interviewing"])]))

        st.write("")
        b_col1, b_col2, _ = st.columns([1.5, 1.5, 3])

        with b_col1:
            if st.button("Score All Unscored", use_container_width=True):
                unscored = [a for a in applications if a.match_score == 0.0 or a.status == "Scraped"]
                if not unscored:
                    st.info("All listings already scored.")
                else:
                    progress_bar = st.progress(0)
                    matcher = JobMatcher(base_resume_text=active_resume_text)
                    for idx, app in enumerate(unscored):
                        res = matcher.analyze_match(app.title, app.company, app.description or "")
                        if res:
                            db.update_application(app.id, match_score=res.match_score, match_reason=res.reasoning, status="Scored")
                        progress_bar.progress((idx + 1) / len(unscored))
                    st.success("Scoring complete!")
                    st.rerun()

        with b_col2:
            if st.button("Draft Mails (>70% Match)", use_container_width=True):
                top_apps = [a for a in applications if (a.match_score or 0) >= 70.0 and not a.email_draft_body]
                if not top_apps:
                    st.info("No high matches needing drafts.")
                else:
                    progress_bar = st.progress(0)
                    writer = DraftWriter(base_resume_text=active_resume_text)
                    for idx, app in enumerate(top_apps):
                        res = writer.generate_application_draft(
                            job_title=app.title,
                            job_company=app.company,
                            job_description=app.description or "",
                            recipient_name=app.author_name or "Hiring Manager",
                            match_score=app.match_score,
                            match_reasoning=app.match_reason or ""
                        )
                        if res:
                            em, rt = res
                            db.update_application(
                                app.id,
                                email_draft_subject=em.subject,
                                email_draft_body=em.body,
                                tailored_resume_text=rt.tailored_sections,
                                status="Tailored"
                            )
                        progress_bar.progress((idx + 1) / len(top_apps))
                    st.success("Draft generation complete!")
                    st.rerun()

    st.divider()

    # --- FEED ---
    if df.empty:
        st.info("No listings scraped yet. Click Start Scrape above to fetch live openings.")
        return

    filtered_df = df.copy()
    if search_filter:
        mask = (
            filtered_df["title"].str.contains(search_filter, case=False, na=False) |
            filtered_df["company"].str.contains(search_filter, case=False, na=False) |
            filtered_df["description"].str.contains(search_filter, case=False, na=False)
        )
        filtered_df = filtered_df[mask]

    if source_filter != "All":
        clean_source = "posts" if "posts" in source_filter else "jobs"
        filtered_df = filtered_df[filtered_df["source_type"] == clean_source]

    if status_filter != "All":
        filtered_df = filtered_df[filtered_df["status"] == status_filter]

    filtered_df = filtered_df[filtered_df["match_score"] >= min_score_filter]

    st.markdown(f"#### Feed ({len(filtered_df)} items)")

    for _, row in filtered_df.iterrows():
        source_badge = "POST" if row["source_type"] == "posts" else "JOB"
        status_icon = "●" if row["status"] in ["Applied", "Interviewing"] else "○" if row["status"] == "Tailored" else "·"
        score_badge = f"{row['match_score']:.0f}%" if row["match_score"] > 0 else "Unscored"
        email_flag = f"  |  {row['contact_info']}" if row["contact_info"] else ""

        card_title = f"{status_icon}  [{source_badge}]  **{row['company']}** — {row['title']}  |  Match: **{score_badge}**{email_flag}"

        with st.expander(card_title, expanded=False):
            t1, t2, t3 = st.tabs(["Details & AI", "Email Outreach", "Tailored Resume"])

            with t1:
                col_left, col_right = st.columns([2, 1])
                with col_left:
                    st.markdown(f"**Location:** {row['location']}")
                    if row["contact_info"]:
                        st.markdown(f"**Direct Contact:** `{row['contact_info']}`")
                    st.markdown(f"[View Original on LinkedIn]({row['link']})")
                    st.markdown("**Original Description:**")
                    st.text_area(
                        "Post Body",
                        value=row["description"] if row["description"] else "(No description stored)",
                        height=150,
                        disabled=True,
                        key=f"desc_{row['id']}"
                    )
                with col_right:
                    st.markdown("**AI Match Score**")
                    st.progress(min(1.0, row["match_score"] / 100.0))
                    st.info(row["match_reason"])
                    if st.button("Score this item", key=f"score_single_{row['id']}"):
                        matcher = JobMatcher(base_resume_text=active_resume_text)
                        res = matcher.analyze_match(row["title"], row["company"], row["description"])
                        if res:
                            db.update_application(row["id"], match_score=res.match_score, match_reason=res.reasoning, status="Scored")
                            st.rerun()

                st.divider()
                st.markdown("**Update Status**")
                sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                if sc1.button("Applied", key=f"app_btn_{row['id']}"):
                    db.update_application(row["id"], status="Applied")
                    st.rerun()
                if sc2.button("Interviewing", key=f"int_btn_{row['id']}"):
                    db.update_application(row["id"], status="Interviewing")
                    st.rerun()
                if sc3.button("Offer", key=f"off_btn_{row['id']}"):
                    db.update_application(row["id"], status="Offer")
                    st.rerun()
                if sc4.button("Rejected", key=f"rej_btn_{row['id']}"):
                    db.update_application(row["id"], status="Rejected")
                    st.rerun()
                if sc5.button("Delete", key=f"del_btn_{row['id']}"):
                    db.delete_application(row["id"])
                    st.rerun()

            with t2:
                st.markdown("**Outreach Email**")
                if not row["email_body"]:
                    if st.button("Generate AI Email Draft", key=f"gen_draft_{row['id']}"):
                        writer = DraftWriter(base_resume_text=active_resume_text)
                        res = writer.generate_application_draft(
                            job_title=row["title"],
                            job_company=row["company"],
                            job_description=row["description"],
                            recipient_name=row["author_name"] or "Hiring Manager",
                            match_score=row["match_score"],
                            match_reasoning=row["match_reason"]
                        )
                        if res:
                            em, rt = res
                            db.update_application(
                                row["id"],
                                email_draft_subject=em.subject,
                                email_draft_body=em.body,
                                tailored_resume_text=rt.tailored_sections,
                                status="Tailored"
                            )
                            st.rerun()

                subj_input = st.text_input("Subject", value=row["email_subject"], key=f"subj_in_{row['id']}")
                body_input = st.text_area("Body (Editable)", value=row["email_body"], height=180, key=f"body_in_{row['id']}")
                default_recip = row["contact_info"].split(",")[0].strip() if row["contact_info"] else ""
                recip_email = st.text_input("Recipient Email", value=default_recip, key=f"recip_in_{row['id']}")

                c_save, c_send = st.columns(2)
                if c_save.button("Save Draft", key=f"save_dr_{row['id']}"):
                    db.update_application(row["id"], email_draft_subject=subj_input, email_draft_body=body_input, contact_info=recip_email)
                    st.success("Draft saved!")
                if c_send.button("Send Email", key=f"send_dr_{row['id']}"):
                    if not recip_email or "@" not in recip_email:
                        st.error("Please enter a valid recipient email address.")
                    else:
                        mailer = EmailClient()
                        attachment = None
                        if row["tailored_resume"]:
                            compiler = ResumeCompiler()
                            safe_company = "".join(c for c in row["company"] if c.isalnum() or c in (" ", "_")).rstrip().replace(" ", "_")
                            out_path = f"./data/Tailored_Resume_{safe_company[:20]}.docx"
                            if compiler.compile_to_docx(row["tailored_resume"], out_path):
                                attachment = out_path
                        if mailer.send(to_email=recip_email, subject=subj_input, body=body_input, attachment_path=attachment):
                            db.update_application(row["id"], status="Applied")
                            st.success(f"Email sent to {recip_email}!")
                            st.rerun()
                        else:
                            st.error("Failed to send email. Check SMTP settings.")

            with t3:
                st.markdown("**Tailored Resume Recommendations**")
                st.text_area(
                    "Tailored Highlights",
                    value=row["tailored_resume"] if row["tailored_resume"] else "Generate an email draft to produce tailored bullet points.",
                    height=160,
                    key=f"res_tailor_{row['id']}"
                )
                if row["tailored_resume"]:
                    if st.button("Export as DOCX", key=f"exp_docx_{row['id']}"):
                        compiler = ResumeCompiler()
                        safe_company = "".join(c for c in row["company"] if c.isalnum() or c in (" ", "_")).rstrip().replace(" ", "_")
                        out_path = f"./data/Tailored_Resume_{safe_company[:20]}.docx"
                        if compiler.compile_to_docx(row["tailored_resume"], out_path):
                            st.success(f"Exported: `{out_path}`")


# --- Navigation ---
page = st.sidebar.radio("Navigation", ["Dashboard", "Settings"])

if page == "Settings":
    from src.ui.settings_page import settings_page
    settings_page()
else:
    main_dashboard()
