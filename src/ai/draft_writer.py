from pydantic import BaseModel, Field
from typing import Optional, Tuple
import os
from src.ai.gateway import AIGateway

class EmailDraft(BaseModel):
    subject: str = Field(..., description="Compelling, professional email subject line (under 80 characters).")
    body: str = Field(..., description="Polished, concise, and engaging email body. Include a professional greeting, why my experience matches the job, and a clear call-to-action.")

class ResumeTailored(BaseModel):
    tailored_sections: str = Field(..., description="Key sections of the resume that have been adjusted for this specific role (summary, bullet points, or skills).")
    missing_keywords: str = Field(..., description="The top 3-5 missing skill keywords from my resume that are crucial for this job.")
    linkedin_note: Optional[str] = Field(None, description="Compelling, personalized LinkedIn connection note strictly under 280 characters.")

class CombinedDraftOutput(BaseModel):
    subject: str = Field(..., description="Compelling, professional email subject line (under 80 characters).")
    body: str = Field(..., description="Polished, concise, and engaging email body. Include a professional greeting, why my experience matches the job, and a clear call-to-action.")
    tailored_sections: str = Field(..., description="Key sections of the resume that have been adjusted for this specific role.")
    missing_keywords: str = Field(..., description="The top 3-5 missing skill keywords from my resume that are crucial for this job.")
    linkedin_note: Optional[str] = Field(None, description="Compelling, personalized LinkedIn connection note strictly under 280 characters.")

class LinkedInNoteOutput(BaseModel):
    note: str = Field(..., description="High-converting, personalized LinkedIn connection note strictly under 280 characters.")

class TailoredResumeDoc(BaseModel):
    resume_markdown: str = Field(..., description="Complete rewritten resume in Markdown, tailored to the job. Preserve all truthful facts; weave in missing keywords naturally.")

class DraftWriter:
    def __init__(self, base_resume_text: Optional[str] = None, gateway: Optional[AIGateway] = None):
        self.ai_gateway = gateway or AIGateway(purpose="drafts")
        if base_resume_text:
            self.base_resume_text = base_resume_text
        else:
            base_resume_path = "./data/base_resume.md"
            if os.path.exists(base_resume_path):
                with open(base_resume_path, "r", encoding="utf-8") as f:
                    self.base_resume_text = f.read()
            else:
                self.base_resume_text = "No resume provided."

    def generate_linkedin_note(
        self,
        job_title: str,
        job_company: str,
        recipient_name: str = "Hiring Manager",
        job_description: str = ""
    ) -> str:
        """Generate a punchy, warm, high-converting LinkedIn Connection Note strictly under 280 chars."""
        clean_rec = recipient_name.split()[0] if recipient_name and recipient_name != "Hiring Manager" else "there"
        clean_title = (job_title or "Role").split("|")[0].split("-")[0].strip()
        clean_company = (job_company or "your team").split("(")[0].strip()

        prompt = f"""
# Job & Recruiter Details
Role: {clean_title}
Company: {clean_company}
Recruiter Name: {recipient_name}
Snippet: {job_description[:700] if job_description else ""}

# Candidate Resume
{self.base_resume_text[:1000]}

# Task
Write a natural, high-converting LinkedIn connection request note to {recipient_name}.
CRITICAL CONSTRAINTS:
1. STRICT LIMIT: Must be UNDER 280 CHARACTERS total (spaces included). Absolute hard ceiling.
2. Directly mention interest in the {clean_title} role at {clean_company}.
3. State 1 concrete value proposition or skill alignment from candidate background.
4. Courteous closing asking to connect.
"""
        try:
            res = self.ai_gateway.generate_structured_output(prompt, LinkedInNoteOutput)
            if res and res.note:
                note = res.note.strip()
                if len(note) > 290:
                    note = note[:287] + "..."
                return note
        except Exception:
            pass

        # High-converting deterministic fallback under 270 chars
        fallback = f"Hi {clean_rec}, came across your {clean_title} opening at {clean_company}. My background aligns closely with your tech stack, and I'd love to connect to discuss how I can add immediate value!"
        return fallback[:280]

    def generate_application_draft(
        self,
        job_title: str,
        job_company: str,
        job_description: str,
        recipient_name: str = "Hiring Manager",
        match_score: float = 85.0,
        match_reasoning: str = ""
    ) -> Optional[Tuple[EmailDraft, ResumeTailored]]:
        # Truncate overly long job descriptions to save tokens
        if len(job_description) > 15000:
            job_description = job_description[:15000] + "\n...[TRUNCATED]"

        task_instruction = os.getenv("SYSTEM_PROMPT_EMAIL")
        if not task_instruction or not task_instruction.strip():
            task_instruction = (
                "You have three goals:\n"
                "1. Draft a Tailored Professional Email (Under 200 words, direct hook, clear CTA).\n"
                "2. Suggest 3-4 bullet-point improvements to my resume to align closely with this opening, along with missing keywords.\n"
                "3. Draft a warm, compelling LinkedIn Connection Note under 280 characters."
            )

        prompt = f"""
# Job Application Details
Title: {job_title}
Company: {job_company}
Recipient: {recipient_name}
Job / Post Description:
{job_description}

# My Resume
{self.base_resume_text}

# Additional Context
Match Score: {match_score}/100
Match Reasoning: {match_reasoning}

# Task
{task_instruction}
"""
        combined = self.ai_gateway.generate_structured_output(prompt, CombinedDraftOutput)

        if combined:
            email_draft = EmailDraft(subject=combined.subject, body=combined.body)
            ln_note = combined.linkedin_note or self.generate_linkedin_note(job_title, job_company, recipient_name, job_description)
            resume_tailored = ResumeTailored(
                tailored_sections=combined.tailored_sections,
                missing_keywords=combined.missing_keywords,
                linkedin_note=ln_note
            )
            return email_draft, resume_tailored
        return None

    def generate_tailored_resume(
        self,
        job_title: str,
        job_company: str,
        job_description: str
    ) -> Optional[str]:
        """Full resume rewrite tailored to one JD. Returns Markdown or None."""
        if len(job_description) > 8000:
            job_description = job_description[:8000] + "\n...[TRUNCATED]"

        prompt = f"""
# Target Role
Title: {job_title}
Company: {job_company}
Description:
{job_description}

# My Current Resume
{self.base_resume_text}

# Task
Rewrite my COMPLETE resume tailored to this role, returned as Markdown
with the same sections (Summary, Experience, Skills, Education).
Rules:
1. Preserve every truthful fact — never invent employers, titles, dates, or metrics.
2. Weave the role's key skills/keywords naturally into bullets and skills.
3. Reorder and emphasize the most relevant experience first.
4. Keep it to one page worth of content.
"""
        doc = self.ai_gateway.generate_structured_output(prompt, TailoredResumeDoc)
        return doc.resume_markdown if doc else None
