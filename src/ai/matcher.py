from pydantic import BaseModel, Field
from typing import Optional
import os
from src.ai.gateway import AIGateway


class MatchAnalysis(BaseModel):
    match_score: float = Field(..., description="A score from 0.0 to 100.0 indicating how well the resume matches the job description.")
    reasoning: str = Field(..., description="Crucial, concise explanation of why this score was given, and key skills that are missing.")


class JobMatcher:
    def __init__(self, base_resume_text: Optional[str] = None, gateway: Optional[AIGateway] = None):
        self.ai_gateway = gateway or AIGateway(purpose="scoring")
        if base_resume_text:
            self.base_resume_text = base_resume_text
        else:
            base_resume_path = "./data/base_resume.md"
            if os.path.exists(base_resume_path):
                with open(base_resume_path, "r", encoding="utf-8") as f:
                    self.base_resume_text = f.read()
            else:
                self.base_resume_text = "No resume provided."

    def analyze_match(self, job_title: str, job_company: str, job_description: str) -> Optional[MatchAnalysis]:
        # Truncate overly long descriptions to avoid credit burn
        if len(job_description) > 8000:
            job_description = job_description[:8000] + "\n...[TRUNCATED]"

        goal_instruction = os.getenv("SYSTEM_PROMPT_SCORING")
        if not goal_instruction or not goal_instruction.strip():
            goal_instruction = (
                "As an expert ATS auditor and career coach:\n"
                "1. Rate the alignment between my authentic experience and the requirements in the job description (0-100%).\n"
                "2. Provide concise reasoning (2-3 sentences). Mention any crucial skill-keywords or qualifications that are missing from my resume but required for the job."
            )

        prompt = f"""
# Job to Analyze
Title: {job_title}
Company: {job_company}
Description:
{job_description}

# Reference: My Resume
{self.base_resume_text}

# Goal
{goal_instruction}
"""
        return self.ai_gateway.generate_structured_output(prompt, MatchAnalysis)
