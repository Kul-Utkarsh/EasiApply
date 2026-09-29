"""
Kinetic Neo-Tech Production Server
FastAPI backend powering the Stitch UI, DB, AI Gateway, Scraper Daemon & Resume Manager.

State model: every screen has 4 design states (default / loading / success / error).
The routes below pick the folder for the section's *current* state, so a first-time
login lands on the empty-state designs and a returning user lands on the filled ones.
"""
import os
import re
import csv
import io
import shutil
import sys
import json
import time
import sqlite3
import threading
import uuid
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse, Response
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.storage.db import DatabaseManager
from src.utils.resume_manager import ResumeManager

# Initialize paths & services
DB_PATH = BASE_DIR / "data" / "applications.db"
RESUMES_DIR = BASE_DIR / "data" / "resumes"
PROFILE_PREFS_PATH = BASE_DIR / "data" / "user_profile.json"
db_mgr = DatabaseManager(str(DB_PATH))
resume_mgr = ResumeManager(str(RESUMES_DIR))

def _utc_now():
    return datetime.now(timezone.utc)


def get_user_profile() -> Dict[str, Any]:
    """Load user-defined target profile and domain preferences from disk."""
    if PROFILE_PREFS_PATH.exists():
        try:
            with open(PROFILE_PREFS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_user_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """Save user-defined target profile preferences."""
    PROFILE_PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = get_user_profile()
    existing.update(data)
    with open(PROFILE_PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    return existing


# -----------------------------------------------------------------------------
# Global In-Memory Activity Log Ring Buffer
# -----------------------------------------------------------------------------
ACTIVITY_LOGS: List[Dict[str, Any]] = []
LOG_LOCK = threading.Lock()
_LOG_SEQ = 0


# -----------------------------------------------------------------------------
# Scrape Session Lifecycle (single-flight + cooperative stop)
# -----------------------------------------------------------------------------
SCRAPE_LOCK = threading.Lock()
SERVER_INSTANCE_ID = str(uuid.uuid4())
SCRAPE_STATE: Dict[str, Any] = {
    "running": False,
    "stop_requested": False,
    "started_at": None,
    "instance_id": SERVER_INSTANCE_ID,
    "session_scraped_count": 0
}


def scrape_should_stop() -> bool:
    """Cooperative-stop flag polled by the worker and the Playwright scraper."""
    with SCRAPE_LOCK:
        return bool(SCRAPE_STATE["stop_requested"])


def format_duration(seconds: float) -> str:
    """Format duration in seconds into human-readable e.g. 18s or 1m 24s."""
    secs = int(round(seconds))
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    rem = secs % 60
    return f"{mins}m {rem}s" if rem > 0 else f"{mins}m"


def add_log(status_tag: str, description: str):
    """Append an activity entry stamped with the machine's local wall-clock time."""
    global _LOG_SEQ
    with LOG_LOCK:
        _LOG_SEQ += 1
        now = datetime.now()
        ACTIVITY_LOGS.append({
            "id": _LOG_SEQ,
            "timestamp": now.strftime("%H:%M:%S"),
            "iso_time": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "status_tag": status_tag,
            "description": description,
        })
        if len(ACTIVITY_LOGS) > 300:
            ACTIVITY_LOGS.pop(0)


# Ensure project structure & clean state on startup if requested
def clear_state_on_startup():
    """Clear transient state on application startup if CLEAR_STATE_ON_STARTUP is true"""
    clear_state = os.getenv("CLEAR_STATE_ON_STARTUP", "false").lower() == "true"
    
    if not clear_state:
        with LOG_LOCK:
            ACTIVITY_LOGS.clear()
        recovered = db_mgr.recover_stranded_outbox()
        msg = "Kinetic Neo-Tech Core Agent initialized. Database online."
        if recovered:
            msg += f" (Recovered {recovered} stranded outbox email(s) back to queue)"
        add_log("SYS_INIT", msg)
        return
    
    try:
        with LOG_LOCK:
            ACTIVITY_LOGS.clear()
        if RESUMES_DIR.exists():
            shutil.rmtree(RESUMES_DIR)
            RESUMES_DIR.mkdir(parents=True, exist_ok=True)
        db_mgr.clear_all_applications()
        add_log("SYS_INIT", "Workspace started with CLEAN STATE - all data cleared")
    except Exception as e:
        add_log("ERR_INIT", f"Failed to clear state on startup: {str(e)}")

clear_state_on_startup()

app = FastAPI(title="LinkedIn Job Agent Kinetic Neo-Tech")

LOCAL_ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
_extra_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
if _extra_origins:
    LOCAL_ALLOWED_ORIGINS.extend([o.strip() for o in _extra_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Force browsers to revalidate HTML/JS on every request so UI fixes show
    on next navigation instead of serving a stale cached copy."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path.startswith("/ui/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


app.add_middleware(NoCacheMiddleware)


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Themed 404 page (spec: root DESIGN.md error states)."""
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=404, content={"detail": "Not found."})
    return FileResponse(str(UI_DIR / "404.html"), status_code=404)


@app.exception_handler(500)
async def server_error_handler(request, exc):
    """Themed 500 page; API callers still get JSON."""
    add_log("ERR_500", f"Unhandled error on {request.url.path}: {str(exc)[:200]}")
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})
    return FileResponse(str(UI_DIR / "500.html"), status_code=500)

# Mount static and UI paths (create dirs so StaticFiles never crashes on first run)
STATIC_DIR = BASE_DIR / "frontend" / "static"
UI_DIR = BASE_DIR / "frontend"
(BASE_DIR / "data" / "resumes").mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
UI_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/ui",     StaticFiles(directory=str(UI_DIR)),     name="ui")

# -----------------------------------------------------------------------------
# Env Helpers
# -----------------------------------------------------------------------------
ENV_PATH = BASE_DIR / ".env"


SENSITIVE_ENV_KEYS = {
    "SMTP_PASSWORD",
    "AI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OMNIROUTE_API_KEY",
    "LINKEDIN_LI_AT",
    "LINKEDIN_JSESSIONID",
}

MASKED_SECRET_PLACEHOLDER = "••••••••••••"


def is_masked_secret(val: Any) -> bool:
    """Check if a string represents a masked credential placeholder."""
    if val is None:
        return False
    s = str(val).strip()
    if not s:
        return False
    if s == MASKED_SECRET_PLACEHOLDER:
        return True
    return bool(re.match(r"^[\*•\.\s]+$", s)) or s in {"__MASKED__", "********", "••••••••"}


def get_masked_settings() -> Dict[str, str]:
    """Return environment settings with sensitive credentials masked for security."""
    raw = load_env_dict()
    masked = {}
    for k, v in raw.items():
        is_secret = (
            k in SENSITIVE_ENV_KEYS
            or any(k.endswith(sfx) for sfx in ("_PASSWORD", "_KEY", "_SECRET", "_TOKEN"))
            or "COOKIE" in k
        )
        if is_secret:
            masked[k] = MASKED_SECRET_PLACEHOLDER if (v and str(v).strip()) else ""
        else:
            masked[k] = v
    return masked


def load_env_dict() -> Dict[str, str]:
    env_vars = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    val = v.strip().strip("\"'")
                    val = val.replace(r"\n", "\n")
                    env_vars[k.strip()] = val
    return env_vars


def save_env_dict(updates: Dict[str, Any]):
    current = load_env_dict()
    for k, v in updates.items():
        if v is not None:
            # If incoming value is a masked placeholder, preserve existing credential
            is_secret = (
                k in SENSITIVE_ENV_KEYS
                or any(k.endswith(sfx) for sfx in ("_PASSWORD", "_KEY", "_SECRET", "_TOKEN"))
                or "COOKIE" in k
            )
            if is_secret and is_masked_secret(v):
                continue
            val_str = str(v)
            if k in ("SMTP_PASSWORD", "smtp_password"):
                val_str = val_str.replace(" ", "")
            current[k] = val_str
            os.environ[k] = val_str
    lines = []
    for k, v in current.items():
        escaped_v = v.replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\n")
        if " " in escaped_v or "@" in escaped_v or escaped_v == "" or r"\n" in escaped_v:
            lines.append(f'{k}="{escaped_v}"')
        else:
            lines.append(f"{k}={escaped_v}")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def ai_configured() -> bool:
    """True when a usable AI provider is configured in .env (canonical or legacy keys)."""
    env = load_env_dict()
    if not env:
        return False
    # Explicit keys in .env
    has_key = bool(env.get("AI_API_KEY") or env.get("OMNIROUTE_API_KEY") or env.get("OPENAI_API_KEY") or env.get("OPENROUTER_API_KEY"))
    provider = env.get("AI_PROVIDER", "").lower()
    if provider in ("ollama", "custom"):
        return bool(env.get("AI_BASE_URL"))
    return has_key


# -----------------------------------------------------------------------------
# Resume Metadata
# -----------------------------------------------------------------------------
SKILL_KEYWORDS = [
    "figma", "framer", "sketch", "adobe xd", "photoshop", "illustrator", "indesign",
    "after effects", "premiere pro", "procreate", "miro", "notion",
    "design system", "design systems", "user research", "usability testing",
    "wireframe", "wireframing", "prototyping", "prototype", "interaction design",
    "visual design", "user-centered design", "information architecture", "responsive design",
    "auto-layout", "design tokens", "component libraries", "developer handoff",
    "no-code development", "html", "css", "javascript", "typescript", "react", "next.js",
    "vue", "angular", "node", "python", "fastapi", "django", "flask", "sql", "postgresql",
    "mysql", "mongodb", "redis", "docker", "kubernetes", "aws", "azure", "gcp", "git",
    "ci/cd", "terraform", "product design", "product management", "roadmap", "stakeholder",
    "agile", "scrum", "jira", "analytics", "a/b testing", "seo", "content design",
    "accessibility", "wcag", "motion design", "branding", "typography", "machine learning",
    "nlp", "llm", "prompt engineering", "data analysis", "tableau", "power bi", "excel"
]


def extract_skills(text: str, limit: int = 35) -> List[str]:
    """Dynamically extracts all skills from the SKILLS section + keyword dictionary."""
    skills = []
    seen = set()

    # 1. Parse explicit SKILLS block if present in document
    skills_sec = re.search(
        r'(?i)\b(?:SKILLS|CORE COMPETENCIES|TECHNICAL SKILLS|TECH STACK|AREAS OF EXPERTISE)\b[:\s\n]+([\s\S]{30,1200}?)(?=\n[A-Z\s]{4,}|\Z)',
        text or ""
    )
    if skills_sec:
        block = skills_sec.group(1)
        # Remove category labels (e.g. 'Design:', 'Methods:', 'Tools:', 'Languages:')
        block = re.sub(r'(?i)\b[A-Za-z /]+:\s*', ' ', block)
        items = re.split(r'[,•·;\n/|()]+', block)
        for it in items:
            cl = it.strip()
            cl = re.sub(r'^[•·\-\s]+|[•·\-\s]+$', '', cl)
            if 2 <= len(cl) <= 32 and cl.lower() not in seen and not re.match(r'^\d+$', cl):
                if cl.upper() in ['UI', 'UX', 'AI', 'ATS', 'HMI', 'API', 'SQL', 'HTML', 'CSS', 'AWS', 'GCP']:
                    fmt = cl.upper()
                elif cl.lower() == "figma":
                    fmt = "Figma"
                elif cl.lower() == "framer":
                    fmt = "Framer"
                else:
                    fmt = cl.title()
                skills.append(fmt)
                seen.add(cl.lower())

    # 2. Match standard dictionary keywords to catch in-context competencies
    lowered = (text or "").lower()
    for kw in SKILL_KEYWORDS:
        if kw in lowered and kw not in seen:
            if kw.upper() in ['UI', 'UX', 'AI', 'ATS', 'HMI', 'API', 'SQL', 'HTML', 'CSS', 'AWS', 'GCP']:
                fmt = kw.upper()
            else:
                fmt = kw.title()
            skills.append(fmt)
            seen.add(kw)

    return skills[:limit]


def extract_target_role_and_headline(lines: List[str], text: str) -> Tuple[str, str]:
    """Dynamically detects candidate's target role and summary tagline."""
    BASE_ROLES = [
        "Product Designer", "UI/UX Designer", "UX Designer", "UI Designer",
        "UX Researcher", "Interaction Designer", "Visual Designer", "Design Systems Lead",
        "Product Manager", "Technical Product Manager", "Product Owner",
        "Software Engineer", "Frontend Engineer", "Backend Engineer", "Full Stack Developer",
        "DevOps Engineer", "Data Scientist", "Data Analyst", "Machine Learning Engineer", "AI Engineer",
        "Engineering Manager", "Brand Designer", "Graphic Designer", "Solutions Architect"
    ]

    role = ""
    headline = ""

    # 1. Check if top lines explicitly mention candidate's professional title
    for ln in lines[:8]:
        ln_clean = ln.strip()
        m_start = re.match(r'^([A-Za-z/ ]{3,35}?)(?:\s+specializing\b|\s+with\b|\s+experienced\b|\s*\||\s*—|\s*-)', ln_clean, flags=re.IGNORECASE)
        cand_str = m_start.group(1).strip() if m_start else ln_clean

        is_senior = bool(re.search(r'\b(?:senior|sr\.?)\b', cand_str, re.IGNORECASE))
        is_lead = bool(re.search(r'\b(?:lead|principal|staff)\b', cand_str, re.IGNORECASE))
        is_junior = bool(re.search(r'\b(?:junior|jr\.?|associate|entry)\b', cand_str, re.IGNORECASE))

        for br in sorted(BASE_ROLES, key=len, reverse=True):
            if re.search(r'\b' + re.escape(br) + r'\b', cand_str, re.IGNORECASE):
                if is_senior and not br.lower().startswith("senior"):
                    role = f"Senior {br}"
                elif is_lead and not (br.lower().startswith("lead") or br.lower().endswith("lead")):
                    role = f"Lead {br}"
                elif is_junior and not br.lower().startswith("junior"):
                    role = f"Junior {br}"
                else:
                    role = br
                headline = ln_clean
                break
        if role:
            break

    if role and headline:
        # Keep headline concise (first sentence or main clause)
        headline = re.split(r'\.\s+', headline)[0].strip().rstrip('.')
        if len(headline) > 90:
            headline = re.split(r'[,;]|\bbridging\b', headline, flags=re.IGNORECASE)[0].strip()

    # 2. Fallback to first role under EXPERIENCE
    if not role:
        exp_m = re.search(r'(?:EXPERIENCE|WORK HISTORY|EMPLOYMENT)[\s\S]{0,120}?\n([A-Za-z /]+?)\s*\|', text, re.IGNORECASE)
        if exp_m:
            cand_exp_role = exp_m.group(1).strip()
            for br in sorted(BASE_ROLES, key=len, reverse=True):
                if re.search(r'\b' + re.escape(br) + r'\b', cand_exp_role, re.IGNORECASE):
                    role = br
                    break
            if not role:
                role = cand_exp_role
            headline = role

    if not role:
        role = "Product Designer" if "figma" in (text or "").lower() else "Professional Practitioner"
        headline = "Verified Career Profile"

    return role, headline


def extract_yoe(text: str) -> Tuple[str, str]:
    """Dynamically calculates Years of Experience strictly from active work history."""
    curr_year = datetime.now().year
    curr_month = datetime.now().month

    # 1. Check explicit mention in summary: e.g. '5+ years of experience', '3 yrs experience'
    explicit = re.search(r'(\d+)\+?\s*(?:years|yrs)(?:\s+of)?\s+(?:experience|in)', text or "", re.IGNORECASE)
    if explicit:
        years = int(explicit.group(1))
        tier = "Senior / Staff Tier" if years >= 7 else "Mid / Senior Tier" if years >= 4 else "Mid-Level Career"
        return f"{years}+ Yrs", tier

    # 2. Extract ONLY the experience section to avoid education / graduation years
    exp_text = ""
    exp_m = re.search(r'(?:EXPERIENCE|WORK HISTORY|PROFESSIONAL EXPERIENCE)[\s\S]*?(?=(?:EDUCATION|PROJECTS|SKILLS|CERTIFICATIONS|$))', text or "", re.IGNORECASE)
    if exp_m:
        exp_text = exp_m.group(0)
    else:
        exp_text = text or ""

    months_map = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
        'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9, 'oct': 10, 'october': 10,
        'nov': 11, 'november': 11, 'dec': 12, 'december': 12
    }

    # Find job date ranges: e.g. 'Aug 2025 – Present', 'May 2024 – Nov 2024', '2023 - 2024'
    range_regex = r'(?i)\b([a-z]{3,9}\.?\s+)?(\d{4})\s*[-–—to]+\s*([a-z]{3,9}\.?\s+)?(\d{4}|present|current)\b'
    matches = re.findall(range_regex, exp_text)

    total_months = 0
    for m in matches:
        m1_str, y1_str, m2_str, y2_str = m
        try:
            y1 = int(y1_str)
            m1 = 1
            if m1_str and m1_str.strip().rstrip('.').lower() in months_map:
                m1 = months_map[m1_str.strip().rstrip('.').lower()]

            y2 = curr_year
            m2 = curr_month
            if y2_str.lower() not in ('present', 'current'):
                y2 = int(y2_str)
                m2 = 12
                if m2_str and m2_str.strip().rstrip('.').lower() in months_map:
                    m2 = months_map[m2_str.strip().rstrip('.').lower()]

            span = (y2 - y1) * 12 + (m2 - m1 + 1)
            if 0 < span < 600:
                total_months += span
        except Exception:
            continue

    if total_months >= 96:
        return f"{total_months // 12}+ Yrs", "Lead / Principal Professional"
    elif total_months >= 60:
        return f"{total_months // 12}+ Yrs", "Senior Practitioner"
    elif total_months >= 36:
        return f"{round(total_months / 12, 1)} Yrs", "Mid-Level Professional"
    elif total_months >= 12:
        y_int = int(total_months // 12)
        label = "1–2 Yrs" if y_int <= 2 else f"{y_int}+ Yrs"
        return label, "Associate / Junior Professional"
    elif total_months > 0:
        return "< 1 Yr", "Early Career / Emerging"

    return "1–2 Yrs", "Industry Experience"


def build_resume_meta(filename: str) -> Optional[Dict[str, Any]]:
    """Parse a stored resume and return display metadata for the Profile screen."""
    if not filename:
        return None
    path = RESUMES_DIR / filename
    if not path.exists():
        return None

    text = resume_mgr.get_resume_text(filename)
    if not text:
        return None

    words = len(text.split())
    pages = max(1, round(words / 500)) if words else 1
    stat = path.stat()

    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
    email = email_match.group(0) if email_match else ""

    phone_match = re.search(r"(\+\d[\d\s().\-]{6,}\d|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)", text or "")
    phone = phone_match.group(0).strip() if phone_match else ""

    def _is_contact_line(ln: str) -> bool:
        low = ln.lower()
        return ("@" in ln or "http" in low or "linkedin" in low or "github" in low
                or bool(re.search(r"\d{3,}[-.\s()]", ln)))

    headline_noise = {"resume", "curriculum", "vitae", "profile", "summary", "contact",
                      "personal", "details", "objective", "about", "professional"}
    credentials = {"pmp", "mba", "phd", "msc", "bsc", "ba", "ma", "cpa", "pe",
                   "pmi-acp", "csm", "psm", "aws", "pmi", "ii", "iii", "iv", "jr", "sr"}

    def _clean_name(ln: str) -> str:
        head = re.split(r"[|,•·–—\-/]", ln, maxsplit=1)[0].strip()
        words = [w.strip(".,") for w in head.split()]
        words = [w for w in words if w.lower().strip(".") not in credentials]
        if not words:
            return ""
        joined = " ".join(words)
        if joined.isupper():
            joined = joined.title()
        return joined

    def _looks_like_name(ln: str) -> bool:
        cleaned = _clean_name(ln)
        if not cleaned or len(cleaned) > 50:
            return False
        words = re.findall(r"[A-Za-z][A-Za-z'’\-]*", cleaned)
        if not 1 <= len(words) <= 5:
            return False
        if not all(w[0].isupper() or w.isupper() for w in words):
            return False
        if set(w.lower().strip(".") for w in words) & headline_noise:
            return False
        return True

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    name = ""
    name_idx = -1
    for i, ln in enumerate(lines[:8]):
        m = re.match(r"(?i)^(?:full\s+)?name\s*[:\-–]\s*(.+)$", ln)
        if m and _looks_like_name(m.group(1)):
            name, name_idx = _clean_name(m.group(1)), i
            break
    if not name:
        for i, ln in enumerate(lines[:5]):
            if _is_contact_line(ln):
                continue
            if _looks_like_name(ln):
                name, name_idx = _clean_name(ln), i
                break
    if not name:
        stem = path.stem or filename
        stem = re.sub(r"[_\-.]+", " ", stem)
        stem = re.sub(r"(?i)\b(resume|cv|curriculum vitae|final|updated|new|v\d+|20\d{2}|\d{4})\b", "", stem)
        name = " ".join(w.capitalize() for w in stem.split()) or "Candidate"

    target_role, headline = extract_target_role_and_headline(lines, text)
    yoe, yoe_sub = extract_yoe(text)
    skills = extract_skills(text)

    # Merge user preferences from local storage if configured
    user_prefs = get_user_profile()
    target_roles = user_prefs.get("target_roles")
    if not target_roles and target_role:
        from src.scraper.query_builder import LinkedInQueryBuilder
        target_roles = LinkedInQueryBuilder.expand_role_synonyms(target_role)
    elif not target_roles:
        target_roles = [target_role] if target_role else ["Product Designer"]

    target_locations = user_prefs.get("target_locations") or ["Remote"]
    if user_prefs.get("target_role"):
        target_role = user_prefs["target_role"]
    elif target_roles:
        target_role = target_roles[0]
    if user_prefs.get("target_seniority"):
        yoe_sub = user_prefs["target_seniority"]

    # Calculate default max acceptable YOE based on candidate's experience
    default_max_yoe = 3 if ("1–2" in yoe or "< 1" in yoe or "Junior" in yoe_sub or "Associate" in yoe_sub) else 6
    max_yoe = int(user_prefs.get("max_yoe", default_max_yoe))

    domain_keywords = user_prefs.get("domain_keywords") or skills[:15]
    exclude_keywords = user_prefs.get("exclude_keywords") or []

    # Merge user's custom skills if any
    custom_skills = user_prefs.get("custom_skills") or []
    for cs in custom_skills:
        if cs.lower() not in [s.lower() for s in skills]:
            skills.append(cs)

    return {
        "filename": filename,
        "name": name,
        "email": email,
        "phone": phone,
        "headline": headline,
        "target_role": target_role,
        "target_roles": target_roles,
        "target_locations": target_locations,
        "yoe": yoe,
        "yoe_sub": yoe_sub,
        "max_yoe": max_yoe,
        "domain_keywords": domain_keywords,
        "exclude_keywords": exclude_keywords,
        "vector_status": "Calibrated",
        "vector_description": "Indexed in local ChromaDB for semantic job compatibility ranking.",
        "ext": path.suffix.lower().lstrip("."),
        "size_kb": round(stat.st_size / 1024, 1),
        "size_label": f"{round(stat.st_size / 1024, 1)} KB" if stat.st_size < 1024 * 1024
                       else f"{round(stat.st_size / (1024 * 1024), 2)} MB",
        "pages": pages,
        "words": words,
        "skills": skills,
        "skill_count": len(skills),
        "uploaded_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        "uploaded_at_ts": stat.st_mtime,
        "preview": text[:300].strip(),
    }


def get_primary_resume_filename() -> Optional[str]:
    """Returns the filename of designated primary resume, or None."""
    profile = get_user_profile()
    primary = profile.get("primary_resume")
    if primary and (RESUMES_DIR / primary).exists():
        return primary
    return None


def get_resume_role_tags() -> Dict[str, str]:
    """Returns filename -> role_tag mapping from user profile."""
    profile = get_user_profile()
    return profile.get("resume_tags") or {}


def list_all_resumes_meta() -> List[Dict[str, Any]]:
    """Metadata list for all resumes stored in data/resumes/."""
    files = [f for f in RESUMES_DIR.glob("*.*")
             if f.suffix.lower() in (".md", ".txt", ".docx", ".pdf")]
    if not files:
        return []

    primary_name = get_primary_resume_filename()
    if not primary_name and files:
        newest = max(files, key=lambda f: f.stat().st_mtime)
        primary_name = newest.name

    tags = get_resume_role_tags()
    result = []
    for f in files:
        meta = build_resume_meta(f.name)
        if meta:
            is_prim = (f.name == primary_name)
            tag = tags.get(f.name) or meta.get("target_role") or "General"
            meta["is_primary"] = is_prim
            meta["role_tag"] = tag
            result.append(meta)

    # Sort primary first, then newest upload
    result.sort(key=lambda x: (not x.get("is_primary", False), -x.get("uploaded_at_ts", 0)))
    return result


def find_best_resume_for_job(job_title: str, job_description: str = "") -> Optional[Tuple[str, str]]:
    """
    Intelligently select the candidate's best-matching resume for a specific job title.
    Returns (filename, resume_text).
    """
    all_resumes = list_all_resumes_meta()
    if not all_resumes:
        return None
    if len(all_resumes) == 1:
        fn = all_resumes[0]["filename"]
        return (fn, resume_mgr.get_resume_text(fn))

    title_lower = (job_title or "").lower()
    title_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", title_lower))

    best_resume = None
    best_score = -1

    for r in all_resumes:
        score = 0
        tag = (r.get("role_tag") or "").lower()
        tag_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", tag))

        # Direct token overlap with role tag
        tag_overlap = title_words.intersection(tag_words)
        score += len(tag_overlap) * 10
        if tag and tag in title_lower:
            score += 15

        # Overlap with target_roles synonyms
        target_roles = [tr.lower() for tr in (r.get("target_roles") or [])]
        for tr in target_roles:
            if tr in title_lower:
                score += 12
            else:
                tr_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", tr))
                score += len(title_words.intersection(tr_words)) * 4

        # Target role field
        t_role = (r.get("target_role") or "").lower()
        if t_role and t_role in title_lower:
            score += 8

        # Primary resume slight tie-breaker
        if r.get("is_primary"):
            score += 2

        if score > best_score:
            best_score = score
            best_resume = r

    chosen_fn = best_resume["filename"] if best_resume else all_resumes[0]["filename"]
    return (chosen_fn, resume_mgr.get_resume_text(chosen_fn))


def latest_resume_meta(preferred_filename: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Primary / active resume metadata in the store, or None on a clean install."""
    tags = get_resume_role_tags()
    primary_name = get_primary_resume_filename()

    if preferred_filename and (RESUMES_DIR / preferred_filename).exists():
        meta = build_resume_meta(preferred_filename)
        if meta:
            meta["is_primary"] = (preferred_filename == primary_name)
            meta["role_tag"] = tags.get(preferred_filename) or meta.get("target_role") or "General"
            return meta

    if primary_name:
        meta = build_resume_meta(primary_name)
        if meta:
            meta["is_primary"] = True
            meta["role_tag"] = tags.get(primary_name) or meta.get("target_role") or "General"
            return meta

    files = [f for f in RESUMES_DIR.glob("*.*")
             if f.suffix.lower() in (".md", ".txt", ".docx", ".pdf")]
    if not files:
        return None
    newest = max(files, key=lambda f: f.stat().st_mtime)
    meta = build_resume_meta(newest.name)
    if meta:
        meta["is_primary"] = True
        meta["role_tag"] = tags.get(newest.name) or meta.get("target_role") or "General"
    return meta


def application_count() -> int:
    try:
        return len(db_mgr.get_all_applications())
    except Exception:
        return 0


def has_scraped_data() -> bool:
    """True when any applications are saved â€” returning users see their data."""
    return application_count() > 0


# -----------------------------------------------------------------------------
# Screen state resolution
# -----------------------------------------------------------------------------
UNIVERSAL_MAP = {
    "dashboard": "dashboard.html",
    "profile": "profile.html",
    "matches": "matches.html",
    "outreach": "outreach.html",
    "applications": "outreach.html",
    "analytics": "analytics.html",
    "settings": "settings.html",
}

def screen_url(section: str) -> str:
    return f"/ui/{UNIVERSAL_MAP.get(section, 'dashboard.html')}"

def pick_screen(section: str) -> str:
    return UNIVERSAL_MAP.get(section, "dashboard.html").replace(".html", "")


# -----------------------------------------------------------------------------
# Pydantic Request Models
# -----------------------------------------------------------------------------
class ScrapeRequest(BaseModel):
    url: Optional[str] = ""
    mode: Optional[str] = "posts"
    keywords: Optional[str] = ""
    keywords_list: Optional[List[str]] = None
    location: Optional[str] = "Remote"
    locations: Optional[List[str]] = None
    max_posts: Optional[int] = 15
    # "collect_and_score" (default) or "collect_only" (no AI calls)
    score_mode: Optional[str] = "collect_and_score"


class SettingsPayload(BaseModel):
    AI_PROVIDER: Optional[str] = None
    AI_BASE_URL: Optional[str] = None
    AI_API_KEY: Optional[str] = None
    AI_MODEL: Optional[str] = None
    AI_MODEL_SCORING: Optional[str] = None
    AI_MODEL_DRAFTS: Optional[str] = None
    # Auto-send throttling (outbox queue)
    AI_SEND_DAILY_CAP: Optional[str] = None
    AI_SEND_INTERVAL_SEC: Optional[str] = None
    AI_SEND_BCC_SELF: Optional[str] = None
    # Legacy & alias keys
    OMNIROUTE_BASE_URL: Optional[str] = None
    OMNIROUTE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: Optional[str] = None
    LINKEDIN_EMAIL: Optional[str] = None
    LINKEDIN_PASSWORD: Optional[str] = None
    LINKEDIN_TARGET_URL: Optional[str] = None
    EASYAPPLY_SELENIUM_SEARCH_URL: Optional[str] = None
    SMTP_SERVER: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[str] = None
    SMTP_USERNAME: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SENDER_EMAIL: Optional[str] = None
    SENDER_NAME: Optional[str] = None
    SYSTEM_PROMPT_EXTRACTION: Optional[str] = None
    SYSTEM_PROMPT_SCORING: Optional[str] = None
    SYSTEM_PROMPT_EMAIL: Optional[str] = None

    model_config = {"extra": "allow"}


class ErrorReport(BaseModel):
    section: Optional[str] = "dashboard"
    message: Optional[str] = ""


# -----------------------------------------------------------------------------
# Routes & UI Nav  (state-aware)
def _section_redirect(request: Request, section: str):
    dest = screen_url(section)
    if request.url.query:
        dest = f"{dest}?{request.url.query}"
    return RedirectResponse(url=dest, status_code=307)


@app.get("/")
def root(request: Request):
    return _section_redirect(request, "dashboard")


@app.get("/dashboard")
def dashboard_route(request: Request):
    return _section_redirect(request, "dashboard")


@app.get("/profile")
def profile_route(request: Request):
    return _section_redirect(request, "profile")


@app.get("/matches")
def matches_route(request: Request):
    return _section_redirect(request, "matches")


@app.get("/outreach")
def outreach_route(request: Request):
    return _section_redirect(request, "outreach")


@app.get("/applications")
def applications_route(request: Request):
    return _section_redirect(request, "applications")


@app.get("/analytics")
def analytics_route(request: Request):
    return _section_redirect(request, "analytics")


@app.get("/settings")
def settings_route(request: Request):
    return _section_redirect(request, "settings")


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/state")
def get_state():
    """Single source of truth for which design state each screen should render."""
    resume = latest_resume_meta()
    env = load_env_dict()

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_sent = len([r for r in db_mgr.get_outbox(status="sent") if (r.get("sent_at") or "").startswith(today_str)])
    daily_cap = int(env.get("AI_SEND_DAILY_CAP") or 20)

    return {
        "has_applications": has_scraped_data(),
        "application_count": application_count(),
        "has_resume": resume is not None,
        "resume": resume,
        "has_ai_config": ai_configured(),
        "has_email": bool(env.get("SENDER_EMAIL") and env.get("SMTP_HOST")),
        "sender_name": env.get("SENDER_NAME", ""),
        "sender_email": env.get("SENDER_EMAIL", ""),
        "today_sent_count": today_sent,
        "daily_send_cap": daily_cap,
        "has_linkedin": bool(env.get("LINKEDIN_TARGET_URL") or (_read_linkedin_session() and _read_linkedin_session().get("logged_in") is True)),
        "server_instance_id": SERVER_INSTANCE_ID,
        "session_scraped_count": SCRAPE_STATE.get("session_scraped_count", 0),
        "server_time": datetime.now().strftime("%H:%M:%S"),
        "server_date": datetime.now().strftime("%A, %d %b %Y"),
        "screens": {
            section: screen_url(section)
            for section in ("dashboard", "profile", "matches", "outreach", "analytics", "settings")
        },
    }


@app.get("/api/applications")
def get_applications():
    """Retrieve all scraped and analyzed applications."""
    try:
        apps = db_mgr.get_all_applications()
        result = []
        for a in apps:
            result.append({
                "id": a.id,
                "job_id": a.job_id,
                "title": a.title,
                "company": a.company,
                "location": a.location,
                "link": a.link,
                "description": a.description or "",
                "match_score": int(a.match_score) if a.match_score else 0,
                "match_reason": a.match_reason or "",
                "ats_score": int(a.ats_score) if getattr(a, "ats_score", None) else 0,
                "ats_breakdown": getattr(a, "ats_breakdown", None) or "",
                "status": a.status or "Scraped",
                "source_type": a.source_type or "jobs",
                "contact_info": a.contact_info or "",
                "author_name": a.author_name or "",
                "author_profile_url": getattr(a, "author_profile_url", None) or "",
                "email_draft_subject": a.email_draft_subject or "",
                "email_draft_body": a.email_draft_body or "",
                "tailored_resume_text": a.tailored_resume_text or "",
                "missing_keywords": getattr(a, "missing_keywords", None) or "",
                "resume_used": a.resume_used or "",
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else ""
            })
        return result
    except Exception as e:
        add_log("ERR_DB", f"Failed fetching applications: {str(e)}")
        return []


class ApplicationUpdatePayload(BaseModel):
    email_draft_subject: Optional[str] = None
    email_draft_body: Optional[str] = None
    linkedin_note: Optional[str] = None
    contact_info: Optional[str] = None
    status: Optional[str] = None
    resume_used: Optional[str] = None


@app.get("/api/applications/{app_id}")
def get_application_detail(app_id: int):
    """Retrieve full details of a specific application."""
    app = db_mgr.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    return {
        "id": app.id,
        "job_id": app.job_id,
        "title": app.title,
        "company": app.company,
        "location": app.location,
        "link": app.link,
        "description": app.description or "",
        "match_score": int(app.match_score) if app.match_score else 0,
        "match_reason": app.match_reason or "",
        "ats_score": int(app.ats_score) if getattr(app, "ats_score", None) else 0,
        "ats_breakdown": getattr(app, "ats_breakdown", None) or "",
        "status": app.status or "Scraped",
        "source_type": app.source_type or "jobs",
        "contact_info": app.contact_info or "",
        "author_name": app.author_name or "",
        "author_profile_url": getattr(app, "author_profile_url", None) or "",
        "email_draft_subject": app.email_draft_subject or "",
        "email_draft_body": app.email_draft_body or "",
        "linkedin_note": getattr(app, "linkedin_note", None) or "",
        "tailored_resume_text": app.tailored_resume_text or "",
        "missing_keywords": getattr(app, "missing_keywords", None) or "",
        "resume_used": app.resume_used or "",
        "created_at": app.created_at.strftime("%Y-%m-%d %H:%M") if app.created_at else ""
    }


@app.post("/api/applications/{app_id}/update")
def update_application_detail(app_id: int, payload: ApplicationUpdatePayload):
    """Update draft or contact info for an application."""
    app = db_mgr.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    data = payload.model_dump(exclude_unset=True)
    if data:
        db_mgr.update_application(app_id, **data)
    return {"status": "success", "message": "Application updated."}



@app.get("/api/logs")
def get_logs(since: int = Query(0, description="Return entries after this ID for incremental polling")):
    """Real-time activity log feed. Pass ?since=<last_id> for incremental polls."""
    with LOG_LOCK:
        if since:
            return [l for l in ACTIVITY_LOGS if l["id"] > since]
        return list(ACTIVITY_LOGS)


@app.post("/api/logs/clear")
def clear_logs():
    """Clear the in-memory activity log deque across all screens."""
    with LOG_LOCK:
        ACTIVITY_LOGS.clear()
    return {"status": "ok", "message": "Activity logs cleared"}


@app.get("/api/resume-meta")
def get_resume_meta():
    """Metadata for the active/primary candidate resume."""
    meta = latest_resume_meta()
    if not meta:
        return JSONResponse({"status": "empty", "resume": None})
    return {"status": "ok", "resume": meta}


@app.get("/api/resumes")
def get_all_resumes():
    """List metadata for all candidate resumes in data/resumes/."""
    resumes = list_all_resumes_meta()
    return {"status": "ok", "resumes": resumes, "count": len(resumes)}


class SetPrimaryResumePayload(BaseModel):
    filename: str


@app.post("/api/resumes/primary")
def set_primary_resume(payload: SetPrimaryResumePayload):
    """Set which resume acts as the primary/default candidate profile."""
    filename = Path(payload.filename).name
    target_path = RESUMES_DIR / filename
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found.")
    save_user_profile({"primary_resume": filename})
    add_log("RESUME", f"Designated '{filename}' as primary resume.")
    meta = build_resume_meta(filename)
    return {"status": "success", "primary_resume": filename, "resume": meta}


class SetResumeTagPayload(BaseModel):
    filename: str
    role_tag: str


@app.post("/api/resumes/tag")
def set_resume_role_tag(payload: SetResumeTagPayload):
    """Assign or edit the role specialization tag for a resume."""
    filename = Path(payload.filename).name
    tag = payload.role_tag.strip()
    if not tag:
        raise HTTPException(status_code=400, detail="Role tag cannot be empty.")
    profile = get_user_profile()
    tags = profile.get("resume_tags") or {}
    tags[filename] = tag
    save_user_profile({"resume_tags": tags})
    add_log("RESUME", f"Updated role tag for '{filename}' -> '{tag}'.")
    return {"status": "success", "filename": filename, "role_tag": tag}


class ProfilePreferencesRequest(BaseModel):
    target_role: Optional[str] = None
    target_roles: Optional[List[str]] = None
    target_locations: Optional[List[str]] = None
    target_seniority: Optional[str] = None
    max_yoe: Optional[int] = None
    domain_keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    custom_skills: Optional[List[str]] = None


@app.get("/api/profile/preferences")
def get_profile_prefs():
    """Returns saved candidate profile preferences merged with active resume defaults."""
    prefs = get_user_profile()
    active_meta = latest_resume_meta()
    has_meta = bool(active_meta and (active_meta.get("target_role") or active_meta.get("skills")))
    has_prefs = bool(prefs and (prefs.get("target_role") or prefs.get("target_roles") or prefs.get("max_yoe") is not None))

    default_role = active_meta.get("target_role", "") if active_meta else ""
    default_roles = active_meta.get("target_roles", [default_role] if default_role else []) if active_meta else []
    default_locations = active_meta.get("target_locations", []) if active_meta else []
    default_seniority = active_meta.get("yoe_sub", "") if active_meta else ""
    default_max_yoe = active_meta.get("max_yoe") if active_meta else None
    default_domain = active_meta.get("domain_keywords", active_meta.get("skills", [])[:12]) if active_meta else []

    target_role = prefs.get("target_role") or default_role
    target_roles = prefs.get("target_roles") or default_roles
    target_locations = prefs.get("target_locations") or default_locations
    target_seniority = prefs.get("target_seniority") or default_seniority
    max_yoe = prefs.get("max_yoe") if "max_yoe" in prefs else default_max_yoe
    domain_keywords = prefs.get("domain_keywords") or default_domain
    exclude_keywords = prefs.get("exclude_keywords") or []
    custom_skills = prefs.get("custom_skills") or []

    return {
        "status": "ok",
        "has_profile": bool(has_meta or has_prefs),
        "preferences": {
            "target_role": target_role,
            "target_roles": target_roles,
            "target_locations": target_locations,
            "target_seniority": target_seniority,
            "max_yoe": max_yoe,
            "domain_keywords": domain_keywords,
            "exclude_keywords": exclude_keywords,
            "custom_skills": custom_skills,
        }
    }


@app.post("/api/profile/preferences")
def update_profile_prefs(req: ProfilePreferencesRequest):
    """Save user-customized target role, seniority, locations, and domain preferences."""
    data = {}
    if req.target_roles is not None:
        data["target_roles"] = [r.strip() for r in req.target_roles if r and r.strip()]
        if data["target_roles"]:
            data["target_role"] = data["target_roles"][0]
    elif req.target_role is not None:
        raw_roles = [r.strip() for r in req.target_role.split(",") if r and r.strip()]
        data["target_roles"] = raw_roles
        data["target_role"] = raw_roles[0] if raw_roles else req.target_role.strip()

    if req.target_locations is not None:
        data["target_locations"] = [loc.strip() for loc in req.target_locations if loc and loc.strip()]

    if req.target_seniority is not None:
        data["target_seniority"] = req.target_seniority.strip()
    if req.max_yoe is not None:
        data["max_yoe"] = int(req.max_yoe)
    if req.domain_keywords is not None:
        data["domain_keywords"] = [k.strip() for k in req.domain_keywords if k.strip()]
    if req.exclude_keywords is not None:
        data["exclude_keywords"] = [k.strip() for k in req.exclude_keywords if k.strip()]
    if req.custom_skills is not None:
        data["custom_skills"] = [k.strip() for k in req.custom_skills if k.strip()]
    saved = save_user_profile(data)
    add_log("PREFS", f"Profile criteria updated: {saved.get('target_role', '')} ({saved.get('target_seniority', '')}, max {saved.get('max_yoe', 3)} YOE)")
    return {"status": "ok", "preferences": saved}


class UniversalCareerProfile(BaseModel):
    primary_role: str = Field(description="Primary job title or discipline, e.g. Senior Product Designer, Full Stack Engineer, Marketing Manager")
    target_roles: List[str] = Field(description="3 to 5 industry-standard target roles and synonyms to search for")
    seniority: str = Field(description="Candidate seniority level: Junior, Mid-Level, Senior, Lead, Staff, Principal, Director")
    max_yoe: int = Field(description="Upper limit of years of experience to consider, typically candidate's YOE + 2")
    target_locations: List[str] = Field(default_factory=lambda: ["Remote"], description="Target locations or Remote/Hybrid/Onsite preferences")
    domain_keywords: List[str] = Field(description="Top 10-15 key industry skills/technologies/methodologies")
    exclude_keywords: List[str] = Field(description="Keywords, roles, or tech the candidate is NOT qualified for or wants to avoid")


def analyze_career_profile_with_ai(resume_text: str) -> Optional[Dict[str, Any]]:
    """
    Uses AI Gateway with candidate model failover to analyze any candidate's resume
    (engineering, design, product, marketing, data, etc.) and extract their
    optimal search and scoring criteria.
    """
    if not resume_text or len(resume_text.strip()) < 40:
        return None
    try:
        from src.ai.gateway import AIGateway
        gw = AIGateway(purpose="career_analysis")
        prompt = f"""
Analyze the candidate's resume below and extract their universal career targeting profile for autonomous LinkedIn job matching.

Resume:
\"\"\"
{resume_text[:4000]}
\"\"\"

Requirements:
1. Primary Role: Main job title or discipline (e.g., 'Product Designer', 'Frontend Engineer', 'Data Scientist', 'Marketing Manager').
2. Target Roles: 3 to 5 realistic target titles and industry synonyms to search for in hiring feeds.
3. Seniority: Level of experience ('Junior', 'Mid-Level', 'Senior', 'Lead', 'Staff', 'Principal', 'Director').
4. Max YOE: Upper limit of YOE to match against (typically current YOE + 2).
5. Target Locations: Candidate locations or remote preferences (default ['Remote']).
6. Domain Keywords: Top 10-15 key industry skills/tools/technologies.
7. Exclude Keywords: 3-8 keywords/anti-patterns to avoid (e.g. intern, unpaid, or unrelated domains).
"""
        parsed = gw.generate_structured_output(prompt, UniversalCareerProfile)
        if parsed:
            return parsed.model_dump()
    except Exception as e:
        print(f"AI profile analysis warning: {e}")
    return None


@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...), role_tag: Optional[str] = Form(None)):
    """Upload resume DOCX/PDF/MD, parse it, auto-analyze candidate profile with AI, and calibrate criteria."""
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file was empty.")

        safe_filename = Path(file.filename or "resume.pdf").name
        if not safe_filename or safe_filename.startswith('.'):
            safe_filename = "uploaded_resume.pdf"

        dest = RESUMES_DIR / safe_filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(content)

        meta = build_resume_meta(safe_filename)
        if meta is None:
            if dest.exists():
                dest.unlink()
            raise HTTPException(status_code=500, detail="Saved file could not be parsed.")

        # Universal AI Career Profile Extraction with seamless local heuristic fallback
        resume_text = resume_mgr.get_resume_text(safe_filename) or ""
        ai_profile = analyze_career_profile_with_ai(resume_text)
        assigned_tag = (role_tag or "").strip()

        if ai_profile:
            detected_role = ai_profile.get("primary_role") or meta.get("target_role") or "General"
            if not assigned_tag:
                assigned_tag = detected_role
            saved_profile = save_user_profile({
                "target_role": detected_role,
                "target_roles": ai_profile.get("target_roles") or meta.get("target_roles"),
                "target_seniority": ai_profile.get("seniority") or meta.get("yoe_sub"),
                "max_yoe": ai_profile.get("max_yoe") or meta.get("max_yoe"),
                "target_locations": ai_profile.get("target_locations") or meta.get("target_locations") or ["Remote"],
                "domain_keywords": ai_profile.get("domain_keywords") or meta.get("domain_keywords"),
                "exclude_keywords": ai_profile.get("exclude_keywords") or meta.get("exclude_keywords"),
            })
            add_log("AI_PROFILE", f"AI Career Profiler calibrated: {saved_profile.get('target_role')} "
                                  f"({saved_profile.get('target_seniority')}, max {saved_profile.get('max_yoe')} YOE, "
                                  f"{len(saved_profile.get('target_roles', []))} target roles indexed)")
        else:
            # Deterministic fallback: auto-expand role synonyms and save profile
            from src.scraper.query_builder import LinkedInQueryBuilder
            detected_role = meta.get("target_role", "")
            if not assigned_tag:
                assigned_tag = detected_role or "General"
            if detected_role:
                synonyms = LinkedInQueryBuilder.expand_role_synonyms(detected_role)
                current_prefs = get_user_profile()
                if not current_prefs.get("target_roles"):
                    save_user_profile({
                        "target_role": detected_role,
                        "target_roles": synonyms,
                        "target_seniority": meta.get("yoe_sub", "Mid-Level"),
                        "max_yoe": meta.get("max_yoe", 4),
                        "target_locations": meta.get("target_locations", ["Remote"]),
                        "domain_keywords": meta.get("domain_keywords", []),
                        "exclude_keywords": meta.get("exclude_keywords", []),
                    })

        # Save role tag and primary designation
        profile = get_user_profile()
        tags = profile.get("resume_tags") or {}
        tags[safe_filename] = assigned_tag
        profile_patch = {"resume_tags": tags}

        # If no primary is set yet, make this newly uploaded resume primary
        current_primary = get_primary_resume_filename()
        if not current_primary:
            profile_patch["primary_resume"] = safe_filename
        save_user_profile(profile_patch)

        meta = build_resume_meta(safe_filename) or {}
        meta["role_tag"] = assigned_tag
        meta["is_primary"] = (safe_filename == get_primary_resume_filename())

        add_log("RESUME", f"Ingested {meta['filename']} [{assigned_tag}] — {meta.get('pages', 1)}p, "
                          f"{meta.get('words', 0)} words, {meta.get('skill_count', 0)} competencies extracted.")
        add_log("VECTOR_EMB", f"Generated profile vector index from {meta['filename']}.")

        return {
            "status": "success",
            "message": "Resume parsed and indexed.",
            "resume": meta,
        }
    except HTTPException:
        raise
    except Exception as e:
        add_log("ERR_RESUME", f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/resume/{filename}")
def delete_resume(filename: str):
    """Remove a stored resume from data/resumes/ and clean up tags & primary assignment."""
    safe_name = Path(filename).name
    path = RESUMES_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume not found.")
    path.unlink()

    # Clean up profile tags & reassign primary if deleted
    profile = get_user_profile()
    tags = profile.get("resume_tags") or {}
    if safe_name in tags:
        tags.pop(safe_name, None)

    update_data = {"resume_tags": tags}
    if profile.get("primary_resume") == safe_name:
        remaining_files = [f for f in RESUMES_DIR.glob("*.*")
                           if f.suffix.lower() in (".md", ".txt", ".docx", ".pdf")]
        if remaining_files:
            newest = max(remaining_files, key=lambda f: f.stat().st_mtime)
            update_data["primary_resume"] = newest.name
        else:
            update_data["primary_resume"] = None
    save_user_profile(update_data)

    add_log("RESUME", f"Deleted resume {safe_name}.")
    return {"status": "deleted", "filename": safe_name}


@app.get("/api/resume/{filename}")
def download_resume(filename: str, download: bool = False):
    """Serve a stored resume file inline in browser by default (or download if download=True)."""
    safe_name = Path(filename).name
    path = RESUMES_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume not found.")
    
    import mimetypes
    media_type, _ = mimetypes.guess_type(str(path))
    if not media_type:
        media_type = "application/pdf" if safe_name.lower().endswith(".pdf") else "application/octet-stream"

    if download:
        return FileResponse(
            path=str(path),
            media_type=media_type,
            filename=path.name,
            content_disposition_type="attachment",
        )
    return FileResponse(
        path=str(path),
        media_type=media_type,
        headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"},
    )



def scraper_log_adapter(msg: str):
    """Bridge LinkedInScraper logs to the live activity ring buffer."""
    msg_clean = msg.strip()
    if not msg_clean:
        return
    tag = "SCRAPER"
    if "ðŸ”‘" in msg_clean or "Login" in msg_clean or "login" in msg_clean:
        tag = "AUTH"
    elif "ðŸ”" in msg_clean or "Navigating" in msg_clean:
        tag = "NAV"
    elif "ðŸ“œ" in msg_clean or "Scrolling" in msg_clean:
        tag = "SCROLL"
    elif "ðŸ’¾" in msg_clean or "Saving" in msg_clean:
        tag = "DB"
    elif "âœ…" in msg_clean or "Finished" in msg_clean:
        tag = "SUCCESS"
    elif "âŒ" in msg_clean or "Error" in msg_clean or "Aborting" in msg_clean:
        tag = "ERR_SCRAPER"
    elif "âš ï¸" in msg_clean or "WARN" in msg_clean:
        tag = "WARN"
    elif "+" in msg_clean or "Collected" in msg_clean:
        tag = "MATCH"
    add_log(tag, msg_clean)


def run_crawler_task(req: ScrapeRequest):
    """Background worker for scraping (supports multiple keywords / locations)."""
    mode = (req.mode or "posts").lower()
    prefs = get_user_profile()
    active_meta = latest_resume_meta()

    saved_roles = prefs.get("target_roles") or ([prefs.get("target_role")] if prefs.get("target_role") else [])
    if not saved_roles and active_meta and active_meta.get("target_role"):
        saved_roles = [active_meta.get("target_role")]
    saved_locs = prefs.get("target_locations") or []

    kw_list = [k.strip() for k in (req.keywords_list or []) if k and k.strip()]
    if not kw_list and req.keywords and req.keywords.strip():
        kw_list = [req.keywords.strip()]
    if not kw_list and saved_roles:
        kw_list = [f"hiring {r.lower()}" if mode == "posts" else r for r in saved_roles]
    if not kw_list:
        kw_list = [f"hiring {saved_roles[0].lower()}"] if (saved_roles and mode == "posts") else (saved_roles if saved_roles else (["hiring"] if mode == "posts" else ["jobs"]))

    loc_list = [loc.strip() for loc in (req.locations or []) if loc and loc.strip()]
    if not loc_list and req.location and req.location.strip():
        loc_list = [req.location.strip()]
    if not loc_list and saved_locs:
        loc_list = saved_locs
    if not loc_list:
        loc_list = ["Remote"]

    t_scrape_start = time.time()
    add_log("SCRAPER", f"Starting Playwright scraper daemon [Mode: {mode.upper()}] "
                       f"[{len(kw_list)} keyword set(s) x {len(loc_list)} location(s)]...")
    try:
        from src.scraper.client import LinkedInScraper
        scraper = LinkedInScraper(log_callback=scraper_log_adapter)

        domain_kw = prefs.get("domain_keywords") or (active_meta.get("domain_keywords") if active_meta else None)
        exclude_kw = prefs.get("exclude_keywords") or (active_meta.get("exclude_keywords") if active_meta else None)
        max_yoe = prefs.get("max_yoe") if prefs.get("max_yoe") is not None else (active_meta.get("max_yoe") if active_meta else 3)
        target_seniority = prefs.get("target_seniority") or (active_meta.get("yoe_sub") if active_meta else None)

        kw_or_url = req.url.strip() if req.url and req.url.strip() else " ".join(kw_list)
        count = 0
        if req.url and req.url.strip():
            # A pasted LinkedIn URL already encodes its own filters — single pass.
            sub = "url-target"
            loc = loc_list[0]
            add_log("SCRAPER", f"Scanning {sub} ...")
            count += scraper.run(
                mode=mode,
                keywords=kw_or_url,
                location=loc,
                limit=req.max_posts or 15,
                should_stop=scrape_should_stop,
                domain_keywords=domain_kw,
                exclude_keywords=exclude_kw,
                max_yoe=max_yoe,
                target_seniority=target_seniority,
                target_roles=saved_roles
            )
        elif mode == "jobs":
            import random as _random
            first_loc = True
            for loc in loc_list:
                if scrape_should_stop():
                    add_log("STOPPED", "Scrape stop requested — halting before next location.")
                    break
                if not first_loc:
                    # Politeness pause between location passes (human-like pacing).
                    pause = round(_random.uniform(4.0, 9.0), 1)
                    add_log("POLITE", f"Politeness pause {pause}s before '{loc}'...")
                    time.sleep(pause)
                    if scrape_should_stop():
                        add_log("STOPPED", "Scrape stop requested during pause.")
                        break
                first_loc = False
                add_log("SCRAPER", f"Scanning '{kw_or_url}' in {loc}...")
                count += scraper.run(
                    mode=mode,
                    keywords=kw_or_url,
                    location=loc,
                    limit=req.max_posts or 15,
                    should_stop=scrape_should_stop,
                    domain_keywords=domain_kw,
                    exclude_keywords=exclude_kw,
                    max_yoe=max_yoe,
                    target_seniority=target_seniority,
                    target_roles=saved_roles
                )
        else:
            # LinkedIn post search has no location filter — one pass, combined keywords.
            count += scraper.run(
                mode=mode,
                keywords=kw_or_url,
                location=loc_list[0],
                limit=req.max_posts or 15,
                should_stop=scrape_should_stop,
                domain_keywords=domain_kw,
                exclude_keywords=exclude_kw,
                max_yoe=max_yoe,
                target_seniority=target_seniority,
                target_roles=saved_roles
            )
        scrape_duration = time.time() - t_scrape_start
        with SCRAPE_LOCK:
            SCRAPE_STATE["collected"] = count
            SCRAPE_STATE["session_scraped_count"] = SCRAPE_STATE.get("session_scraped_count", 0) + count
        if scrape_should_stop():
            add_log("STOPPED", f"Scrape stopped by user in {format_duration(scrape_duration)}. {count} leads collected before stop.")
        elif count > 0:
            add_log("SUCCESS", f"Scrape batch complete in {format_duration(scrape_duration)}. {count} leads ready in database.")
        else:
            add_log("WARN", f"Scrape batch complete in {format_duration(scrape_duration)}. 0 leads collected.")
        # Score unless the user asked for collect-only (or stopped mid-run).
        if not scrape_should_stop():
            if (req.score_mode or "collect_and_score") == "collect_only":
                add_log("COLLECT", f"Collect-only mode — {count} listings saved unscored in {format_duration(scrape_duration)}. Score them later from Matches.")
                with SCRAPE_LOCK:
                    SCRAPE_STATE["last_scan_duration"] = {
                        "scrape_sec": round(scrape_duration, 1),
                        "score_sec": 0.0,
                        "total_sec": round(scrape_duration, 1),
                        "mode": "collect_only"
                    }
                    SCRAPE_STATE["last_scan_summary"] = f"Finished in {format_duration(scrape_duration)} (Scrape only)"
            else:
                add_log("AI_MATCH", f"Scrape complete ({format_duration(scrape_duration)}). Starting AI scoring phase...")
                t_score_start = time.time()
                score_res = score_unscored_apps()
                score_duration = time.time() - t_score_start
                total_duration = scrape_duration + score_duration
                scored_cnt = score_res.get("scored", 0) if isinstance(score_res, dict) else 0
                add_log("SUCCESS", f"Full scan finished in {format_duration(total_duration)} (Scrape: {format_duration(scrape_duration)} • AI Analysis: {format_duration(score_duration)}). {scored_cnt} leads scored.")
                with SCRAPE_LOCK:
                    SCRAPE_STATE["last_scan_duration"] = {
                        "scrape_sec": round(scrape_duration, 1),
                        "score_sec": round(score_duration, 1),
                        "total_sec": round(total_duration, 1),
                        "mode": "collect_and_score"
                    }
                    SCRAPE_STATE["last_scan_summary"] = f"Finished in {format_duration(total_duration)} (Scrape: {format_duration(scrape_duration)} • AI: {format_duration(score_duration)})"
    except Exception as e:
        add_log("ERR_SCRAPER", f"Crawler daemon encountered error: {str(e)}")
    finally:
        with SCRAPE_LOCK:
            SCRAPE_STATE["running"] = False
            SCRAPE_STATE["stop_requested"] = False
            SCRAPE_STATE["started_at"] = None
            SCRAPE_STATE["last_collected"] = SCRAPE_STATE.get("collected", 0)


AI_LOCK = threading.Lock()
AI_STATE: Dict[str, Any] = {"running": False}


def _active_resume(preferred_filename: Optional[str] = None, job_title: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """(filename, text) of the appropriate resume based on candidate's multiple resumes and role routing."""
    if preferred_filename and (RESUMES_DIR / preferred_filename).exists():
        try:
            txt = resume_mgr.get_resume_text(preferred_filename)
            if txt and not txt.startswith("Error") and not txt.startswith("Resume not found"):
                return (preferred_filename, txt)
        except Exception:
            pass

    if job_title:
        matched = find_best_resume_for_job(job_title)
        if matched and matched[1] and not matched[1].startswith("Error") and not matched[1].startswith("Resume not found"):
            return matched

    meta = latest_resume_meta(preferred_filename=preferred_filename)
    if not meta:
        return None
    try:
        text = resume_mgr.get_resume_text(meta["filename"])
    except Exception:
        return None
    if not text or text.startswith("Error") or text.startswith("Resume not found"):
        return None
    return (meta["filename"], text)


def _score_unscored_inner() -> Dict[str, Any]:
    """Score every unscored application concurrently. Caller owns AI_STATE lifecycle."""
    if not ai_configured():
        add_log("SKIP_AI", "AI provider not configured — leaving results unscored.")
        return {"status": "skipped", "reason": "no_ai"}
    active = _active_resume()
    if not active:
        add_log("SKIP_AI", "No resume uploaded — add one on Profile to enable scoring.")
        return {"status": "skipped", "reason": "no_resume"}
    filename, resume_text = active
    from src.ai.matcher import JobMatcher
    from src.ai.ats import score_ats
    import json as _json
    import concurrent.futures

    apps = [a for a in db_mgr.get_all_applications()
            if not (a.match_score or 0) and (a.status or "Scraped") == "Scraped"]
    total = len(apps)
    if not total:
        return {"status": "empty", "scored": 0}

    t_start = time.time()
    add_log("AI_MATCH", f"Scoring {total} unscored listing(s) in parallel (intelligent role-routed across resumes)...")
    scored = 0
    completed_idx = 0
    counter_lock = threading.Lock()
    db_lock = threading.Lock()

    def score_single(app_item):
        nonlocal scored, completed_idx
        if scrape_should_stop():
            return None

        # Determine candidate's best matching resume for this specific job
        matched = _active_resume(preferred_filename=getattr(app_item, "resume_used", None), job_title=app_item.title)
        item_filename, item_resume_text = matched if matched else (filename, resume_text)

        # Free ATS pass first
        try:
            ats = score_ats(item_resume_text, app_item.title, app_item.description or "")
        except Exception:
            ats = {"ats_score": 0, "breakdown": {}, "missing_keywords": []}

        # AI match analysis
        try:
            matcher = JobMatcher(base_resume_text=item_resume_text)
            res = matcher.analyze_match(app_item.title, app_item.company, app_item.description or "")
        except Exception as e:
            add_log("ERR_AI", f"Scoring exception for {app_item.company}: {e}")
            res = None

        if scrape_should_stop():
            return None

        with counter_lock:
            completed_idx += 1
            idx_display = completed_idx

        missing_kw_str = ", ".join(ats.get("missing_keywords", [])) if ats.get("missing_keywords") else ""
        with db_lock:
            if res:
                db_mgr.update_application(
                    app_item.id,
                    ats_score=ats["ats_score"],
                    ats_breakdown=_json.dumps(ats["breakdown"]),
                    missing_keywords=missing_kw_str,
                    match_score=res.match_score,
                    match_reason=res.reasoning,
                    resume_used=item_filename,
                    status="Scored"
                )
                with counter_lock:
                    scored += 1
                add_log("SCORED", f"[{idx_display}/{total}] {app_item.company} — {res.match_score:.0f}% (ATS {ats['ats_score']}%) [via {item_filename}]")
            else:
                ats_fallback_score = float(ats.get("ats_score", 0))
                err_reason = getattr(getattr(matcher, "ai_gateway", None), "last_error", None) or "AI analysis unavailable"
                db_mgr.update_application(
                    app_item.id,
                    ats_score=ats["ats_score"],
                    ats_breakdown=_json.dumps(ats["breakdown"]),
                    missing_keywords=missing_kw_str,
                    match_score=ats_fallback_score,
                    match_reason=f"ATS Match Score: {ats_fallback_score:.0f}%. (AI fallback: {err_reason[:120]})",
                    resume_used=item_filename,
                    status="Scored (ATS)"
                )
                with counter_lock:
                    scored += 1
                add_log("SCORED", f"[{idx_display}/{total}] {app_item.company} — {ats_fallback_score:.0f}% (ATS Fallback) [via {item_filename}]")

        return idx_display

    max_workers = min(3, total)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(score_single, a) for a in apps]
        for f in concurrent.futures.as_completed(futures):
            if scrape_should_stop():
                add_log("STOPPED", "Scoring halted by stop request.")
                executor.shutdown(wait=False, cancel_futures=True)
                break
            try:
                f.result()
            except Exception as e:
                add_log("ERR_AI", f"Worker error: {e}")

    duration = time.time() - t_start
    add_log("SUCCESS" if scored else "WARN",
            f"AI scoring complete in {format_duration(duration)}. {scored}/{total} listing(s) scored.")
    return {"status": "done", "scored": scored, "total": total, "duration_sec": round(duration, 1)}


def score_unscored_apps() -> Dict[str, Any]:
    """Synchronous single-flight scoring (used inline by the scrape worker)."""
    with AI_LOCK:
        if AI_STATE["running"]:
            add_log("SKIP_AI", "Scoring already in progress — skipping duplicate run.")
            return {"status": "busy"}
        AI_STATE["running"] = True
    try:
        return _score_unscored_inner()
    finally:
        with AI_LOCK:
            AI_STATE["running"] = False


def _score_thread() -> None:
    try:
        _score_unscored_inner()
    finally:
        with AI_LOCK:
            AI_STATE["running"] = False


@app.post("/api/score")
def trigger_score():
    """Score all unscored applications in a background thread (on-demand)."""
    with AI_LOCK:
        if AI_STATE["running"]:
            raise HTTPException(status_code=409, detail="Scoring already in progress.")
        AI_STATE["running"] = True
    add_log("QUEUED", "On-demand scoring requested for unscored listings.")
    threading.Thread(target=_score_thread, daemon=True).start()
    return {"status": "started", "message": "Scoring dispatched."}


@app.get("/api/score/status")
def score_status():
    """Whether an on-demand scoring run is active."""
    with AI_LOCK:
        return dict(AI_STATE)


@app.post("/api/applications/{app_id}/draft")
def draft_for_application(app_id: int):
    """Generate (or regenerate) the tailored mail + resume notes for one job."""
    app = db_mgr.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if not ai_configured():
        raise HTTPException(status_code=400, detail="AI provider not configured — set it in Settings first.")
    active = _active_resume(preferred_filename=getattr(app, "resume_used", None), job_title=app.title)
    if not active:
        raise HTTPException(status_code=400, detail="No resume uploaded — add one on Profile first.")
    filename, resume_text = active
    from src.ai.draft_writer import DraftWriter
    writer = DraftWriter(base_resume_text=resume_text)
    try:
        out = writer.generate_application_draft(
            job_title=app.title,
            job_company=app.company,
            job_description=app.description or "",
            recipient_name=app.author_name or "Hiring Manager",
            match_score=app.match_score or 0.0,
            match_reasoning=app.match_reason or "")
    except Exception as e:
        add_log("ERR_AI", f"Draft failed for {app.company}: {e}")
        raise HTTPException(status_code=500, detail=f"Draft generation failed: {e}")
    if not out:
        add_log("ERR_AI", f"Draft returned empty for {app.company}.")
        raise HTTPException(status_code=500, detail="AI returned an empty draft. Try again.")
    em, rt = out
    db_mgr.update_application(
        app.id,
        email_draft_subject=em.subject,
        email_draft_body=em.body,
        linkedin_note=rt.linkedin_note,
        tailored_resume_text=rt.tailored_sections,
        missing_keywords=rt.missing_keywords,
        resume_used=filename,
        status="Tailored")
    add_log("DRAFT", f"Mail & LinkedIn note drafted for {app.company} — {app.title} (using {filename})")
    return {"status": "drafted",
            "email_draft_subject": em.subject,
            "email_draft_body": em.body,
            "linkedin_note": rt.linkedin_note or "",
            "tailored_resume_text": rt.tailored_sections,
            "missing_keywords": rt.missing_keywords or "",
            "resume_used": filename}


@app.post("/api/applications/{app_id}/linkedin-note")
def generate_linkedin_note_for_app(app_id: int):
    """Generate or regenerate a crisp, high-converting LinkedIn Connection Note (<280 chars)."""
    app = db_mgr.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    active = _active_resume(preferred_filename=getattr(app, "resume_used", None), job_title=app.title)
    resume_text = active[1] if active else ""
    from src.ai.draft_writer import DraftWriter
    writer = DraftWriter(base_resume_text=resume_text)
    try:
        note = writer.generate_linkedin_note(
            job_title=app.title,
            job_company=app.company,
            recipient_name=app.author_name or "Hiring Manager",
            job_description=app.description or ""
        )
        db_mgr.update_application(app.id, linkedin_note=note)
        add_log("DRAFT", f"LinkedIn Connection Note generated for {app.company} ({len(note)} chars)")
        return {"status": "success", "linkedin_note": note, "char_count": len(note)}
    except Exception as e:
        add_log("ERR_AI", f"Failed to generate LinkedIn note for {app.company}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _tailored_paths(app_id: int, fmt: str):
    base = BASE_DIR / "data" / "tailored"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"resume_{app_id}.md", base / f"resume_{app_id}.{fmt}"


@app.get("/api/applications/{app_id}/resume")
def tailored_resume_download(app_id: int, format: str = Query("docx", description="docx or pdf")):
    """Serve selected/base candidate resume (or compiled version if available)."""
    app = db_mgr.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    active = _active_resume(preferred_filename=getattr(app, "resume_used", None), job_title=app.title)
    if not active:
        raise HTTPException(status_code=400, detail="No resume uploaded — add one on Profile first.")
    filename, resume_text = active
    safe_path = RESUMES_DIR / filename
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found.")

    media = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"
             if safe_path.suffix.lower() == ".docx"
             else ("application/pdf" if safe_path.suffix.lower() == ".pdf" else "text/plain"))
    return FileResponse(str(safe_path), media_type=media, filename=safe_path.name)


@app.post("/api/scrape")
def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """Dispatch background scraping daemon (single-flight)."""
    # Politeness: never exceed the per-session cap, however large the request.
    try:
        session_cap = max(1, int(os.getenv("MAX_JOBS_PER_SESSION", "25")))
    except (TypeError, ValueError):
        session_cap = 25
    if (req.max_posts or 15) > session_cap:
        add_log("POLITE", f"Limit clamped to session cap ({session_cap}/run).")
        req.max_posts = session_cap
    with SCRAPE_LOCK:
        if SCRAPE_STATE["running"]:
            raise HTTPException(status_code=409, detail="A scrape session is already running.")
        SCRAPE_STATE["running"] = True
        SCRAPE_STATE["stop_requested"] = False
        SCRAPE_STATE["started_at"] = datetime.now().strftime("%H:%M:%S")
        SCRAPE_STATE["target"] = req.keywords or req.url or "Active Criteria"
        SCRAPE_STATE["mode"] = req.mode or "posts"
        SCRAPE_STATE["collected"] = 0
    add_log("QUEUED", f"Job search requested. Target: '{req.keywords or req.url}' (Mode: {req.mode}, Score: {req.score_mode or 'collect_and_score'})")
    background_tasks.add_task(run_crawler_task, req)
    return {"status": "started", "mode": req.mode,
            "score_mode": req.score_mode or "collect_and_score",
            "message": "Agent crawler dispatched."}


@app.get("/api/scrape/status")
def scrape_status():
    """Current scrape session state — polled by the top-bar Stop button."""
    with SCRAPE_LOCK:
        state = dict(SCRAPE_STATE)
    with AI_LOCK:
        state["ai_running"] = AI_STATE["running"]
    return state


@app.post("/api/scrape/stop")
def stop_scrape():
    """Request cooperative stop of the running scrape session."""
    with SCRAPE_LOCK:
        if not SCRAPE_STATE["running"]:
            raise HTTPException(status_code=404, detail="No scrape session is running.")
        SCRAPE_STATE["stop_requested"] = True
    add_log("STOP", "Stop requested — finishing current step and closing browser.")
    return {"status": "stopping", "message": "Stop requested. Finishing current step..."}


@app.get("/api/settings")
def get_settings():
    """Retrieve current settings with sensitive credentials masked."""
    return get_masked_settings()


@app.post("/api/settings")
def update_settings(payload: SettingsPayload):
    """Update settings in .env file — per-card validation."""
    data = payload.model_dump(exclude_unset=True)
    # If called from Complete Setup with empty payload, return per-card error instead of silent success
    if not data:
        raise HTTPException(status_code=400, detail="No settings provided — fill at least one card before saving")
    save_env_dict(data)
    add_log("CONFIG", "Environment settings updated successfully.")
    return {"status": "saved", "message": "Settings updated successfully"}


class TestEmailRequest(BaseModel):
    to_email: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    sender_name: Optional[str] = None

    SENDER_EMAIL: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SENDER_NAME: Optional[str] = None


@app.post("/api/settings/test-email")
def test_email(payload: Optional[TestEmailRequest] = None):
    """Sends a real test email using configured or provided SMTP credentials."""
    import smtplib
    from email.mime.text import MIMEText

    env = load_env_dict()
    user = (
        (payload and (payload.smtp_user or payload.SMTP_USER or payload.to_email or payload.SENDER_EMAIL))
        or env.get("SMTP_USER") or env.get("SMTP_USERNAME") or env.get("SENDER_EMAIL") or ""
    ).strip()
    to_email = (
        (payload and (payload.to_email or payload.SENDER_EMAIL))
        or env.get("SENDER_EMAIL") or user
    ).strip()
    host = (
        (payload and (payload.smtp_host or payload.SMTP_HOST))
        or env.get("SMTP_HOST") or env.get("SMTP_SERVER")
        or ("smtp.gmail.com" if "@gmail.com" in (user or to_email) else "smtp.gmail.com")
    ).strip()
    port_str = (
        (payload and (payload.smtp_port or payload.SMTP_PORT))
        or env.get("SMTP_PORT") or "587"
    ).strip()
    password = (
        (payload and (payload.smtp_password or payload.SMTP_PASSWORD))
        or env.get("SMTP_PASSWORD") or ""
    ).strip().replace(" ", "")
    if is_masked_secret(password):
        password = (env.get("SMTP_PASSWORD") or "").strip().replace(" ", "")
    sender_name = (
        (payload and (payload.sender_name or payload.SENDER_NAME))
        or env.get("SENDER_NAME") or "EasiApply Cockpit"
    ).strip()

    if not host or not user or not password:
        raise HTTPException(
            status_code=400,
            detail="SMTP credentials incomplete. Please configure Host, Port, Username/Email, and App Password in Settings."
        )
    if not to_email:
        raise HTTPException(
            status_code=400,
            detail="No recipient email found. Set your Sender Address in Settings."
        )

    try:
        port = int(port_str) if port_str else 587
    except ValueError:
        port = 587

    try:
        msg = MIMEText(
            "Hello from EasiApply!\n\nThis is a verified test dispatch from your EasiApply job automation cockpit.\nYour SMTP settings are active and operational.",
            "plain",
            "utf-8"
        )
        msg["From"] = f"{sender_name} <{user}>"
        msg["To"] = to_email
        msg["Subject"] = "EasiApply SMTP Test Dispatch"

        server = smtplib.SMTP(host, port, timeout=15)
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_email], msg.as_string())
        server.quit()

        add_log("MAIL_TEST", f"Test email successfully sent to {to_email}")
        save_env_dict({
            "SENDER_EMAIL": to_email,
            "SMTP_USER": user,
            "SMTP_HOST": host,
            "SMTP_PORT": str(port),
            "SMTP_PASSWORD": password,
            "SENDER_NAME": sender_name
        })
        return {"status": "success", "message": f"Test email successfully delivered to {to_email}"}
    except Exception as e:
        add_log("ERR_MAIL", f"SMTP test failed: {str(e)[:150]}")
        raise HTTPException(status_code=400, detail=f"SMTP test failed: {str(e)}")


class TestAIRequest(BaseModel):
    baseUrl: Optional[str] = None
    apiKey: Optional[str] = None
    model: Optional[str] = None
    model_scoring: Optional[str] = None
    model_drafts: Optional[str] = None
    provider: Optional[str] = None
    AI_PROVIDER: Optional[str] = None
    AI_BASE_URL: Optional[str] = None
    AI_API_KEY: Optional[str] = None
    AI_MODEL: Optional[str] = None
    AI_MODEL_SCORING: Optional[str] = None
    AI_MODEL_DRAFTS: Optional[str] = None
    OMNIROUTE_BASE_URL: Optional[str] = None
    OMNIROUTE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: Optional[str] = None

class TestPromptRequest(BaseModel):
    provider: Optional[str] = None
    baseUrl: Optional[str] = None
    apiKey: Optional[str] = None
    model_id: Optional[str] = None
    prompt: str
    temperature: Optional[float] = 0.0

def _run_micro_inference(base_url: str, api_key: str, model_id: str, purpose_label: str) -> Dict[str, Any]:
    """Sends a fast micro-prompt to verify that the model actually responds with tokens."""
    import requests
    import time
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": "Ping. Respond in under 6 words confirming you are online."}
        ],
        "max_tokens": 20,
        "temperature": 0.0
    }
    started = time.time()
    try:
        url = f"{base_url.rstrip('/')}/chat/completions"
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        elapsed_ms = int((time.time() - started) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            reply_text = ""
            if choices and isinstance(choices[0], dict):
                first_choice = choices[0]
                msg = first_choice.get("message")
                raw_val = None
                if isinstance(msg, dict):
                    raw_val = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning")
                if not raw_val:
                    raw_val = first_choice.get("text")
                if raw_val is not None:
                    reply_text = str(raw_val).strip()

            tokens = data.get("usage", {}).get("total_tokens", 0) if isinstance(data, dict) else 0
            return {
                "purpose": purpose_label,
                "model_id": model_id,
                "status": "ok",
                "latency_ms": elapsed_ms,
                "reply": reply_text or "Response received (empty body)",
                "tokens": tokens,
                "error": None
            }
        else:
            err_msg = f"HTTP {resp.status_code}"
            try:
                err_data = resp.json()
                if "error" in err_data:
                    err_detail = err_data["error"]
                    err_msg = err_detail.get("message") if isinstance(err_detail, dict) else str(err_detail)
            except Exception:
                err_msg = resp.text[:120]
            return {
                "purpose": purpose_label,
                "model_id": model_id,
                "status": "error",
                "latency_ms": elapsed_ms,
                "reply": None,
                "tokens": 0,
                "error": err_msg
            }
    except Exception as e:
        elapsed_ms = int((time.time() - started) * 1000)
        return {
            "purpose": purpose_label,
            "model_id": model_id,
            "status": "error",
            "latency_ms": elapsed_ms,
            "reply": None,
            "tokens": 0,
            "error": str(e)
        }

class GatewayModelsRequest(BaseModel):
    apiKey: Optional[str] = None
    api_key: Optional[str] = None
    baseUrl: Optional[str] = None
    base_url: Optional[str] = None
    provider: Optional[str] = None


def _fetch_gateway_models_list(api_key: Optional[str] = None, base_url: Optional[str] = None, provider: Optional[str] = None):
    try:
        env = load_env_dict()
        prov = (provider or env.get("AI_PROVIDER") or "custom").strip().lower()
        from src.ai.providers import PROVIDER_PRESETS
        preset = PROVIDER_PRESETS.get(prov, PROVIDER_PRESETS.get("custom", {}))
        b_url = (base_url or env.get("AI_BASE_URL") or env.get("OMNIROUTE_BASE_URL") or preset.get("base_url", "")).strip()
        k = (api_key or "").strip()
        if is_masked_secret(k) or not k:
            k = (env.get("AI_API_KEY") or env.get("OMNIROUTE_API_KEY") or "").strip()
        requires_key = preset.get("requires_key", True)

        if not b_url:
            return {"status": "ok", "models": [], "active_model": "", "count": 0, "message": "No base URL provided."}
        if requires_key and not k:
            return {"status": "ok", "models": [], "active_model": "", "count": 0, "message": "API key required to discover models."}

        headers = {"Content-Type": "application/json"}
        if k:
            headers["Authorization"] = f"Bearer {k}"

        urls_to_try = [
            f"{b_url.rstrip('/')}/models",
            f"{b_url.rstrip('/v1').rstrip('/')}/v1/models" if "/v1" in b_url else f"{b_url.rstrip('/')}/v1/models"
        ]
        import requests
        discovered = []
        for u in urls_to_try:
            try:
                resp = requests.get(u, headers=headers, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_list = data.get("data") or data.get("models") or []
                    for item in raw_list:
                        m_id = item.get("id") or item.get("name") or (item if isinstance(item, str) else "")
                        if m_id and isinstance(m_id, str):
                            low = m_id.lower()
                            if any(x in low for x in ["whisper", "tts", "dall-e", "embedding", "embed", "moderation", "rerank"]):
                                continue
                            discovered.append(m_id)
                    if discovered:
                        break
            except Exception:
                continue

        seen = set()
        clean_models = []
        for m in discovered:
            if m not in seen:
                seen.add(m)
                clean_models.append(m)

        active_model = env.get("AI_MODEL") or (clean_models[0] if clean_models else "")
        return {
            "status": "ok",
            "models": clean_models,
            "active_model": active_model,
            "count": len(clean_models)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "models": [],
            "active_model": ""
        }


@app.get("/api/gateway/models")
def get_gateway_models_get(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: Optional[str] = None
):
    """Fetches available models directly from the AI gateway via GET."""
    return _fetch_gateway_models_list(api_key=api_key, base_url=base_url, provider=provider)


@app.post("/api/gateway/models")
def get_gateway_models_post(payload: Optional[GatewayModelsRequest] = None):
    """Fetches available models directly from the AI gateway via POST."""
    data = payload.model_dump(exclude_none=True) if payload else {}
    k = data.get("apiKey") or data.get("api_key")
    b = data.get("baseUrl") or data.get("base_url")
    p = data.get("provider")
    return _fetch_gateway_models_list(api_key=k, base_url=b, provider=p)


@app.post("/api/test-ai")
def test_ai(payload: Optional[TestAIRequest] = None):
    """Verify AI provider connectivity, auto-discover models, and test live inference across configured models."""
    from src.ai.providers import PROVIDER_PRESETS
    data = payload.model_dump(exclude_none=True) if payload else {}
    provider = str(data.get("provider") or data.get("AI_PROVIDER") or "custom").strip().lower()
    if provider not in PROVIDER_PRESETS:
        provider = "custom"
    base_url = str(data.get("baseUrl") or data.get("AI_BASE_URL")
                or data.get("OMNIROUTE_BASE_URL") or "").strip()
    api_key = str(data.get("apiKey") or data.get("AI_API_KEY")
               or data.get("OMNIROUTE_API_KEY") or "").strip()
    env = load_env_dict()
    if is_masked_secret(api_key):
        api_key = str(env.get("AI_API_KEY") or env.get("OMNIROUTE_API_KEY") or "").strip()
    if not base_url:
        base_url = str(env.get("AI_BASE_URL") or env.get("OMNIROUTE_BASE_URL") or "").strip()
    model = str(data.get("model") or data.get("AI_MODEL")
             or data.get("CLAUDE_MODEL") or "").strip()
    model_scoring = str(data.get("model_scoring") or data.get("AI_MODEL_SCORING") or "").strip()
    model_drafts = str(data.get("model_drafts") or data.get("AI_MODEL_DRAFTS") or "").strip()

    requires_key = PROVIDER_PRESETS[provider]["requires_key"]
    if not base_url or (requires_key and not api_key):
        missing = []
        if not base_url: missing.append("Base URL")
        if requires_key and not api_key: missing.append("API key")
        msg = f"Missing required: {', '.join(missing)}"
        add_log("ERR_AI", msg)
        raise HTTPException(status_code=400, detail=msg)

    add_log("AI_GATEWAY", f"Testing connection to {PROVIDER_PRESETS[provider]['label']}: {base_url}...")

    # Step 1: Base reachability test (GET /models) and auto-discovery
    discovered_models = []
    gateway_reachable = False
    try:
        import requests
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = requests.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=10)
        gateway_reachable = (resp.status_code == 200)
        if resp.status_code == 200:
            try:
                m_data = resp.json()
                items = m_data.get("data", []) if isinstance(m_data, dict) else (m_data if isinstance(m_data, list) else [])
                for it in items:
                    if isinstance(it, dict) and it.get("id"):
                        discovered_models.append(it["id"])
                    elif isinstance(it, str):
                        discovered_models.append(it)
            except Exception:
                pass
    except Exception as e:
        gateway_reachable = False

    # Auto-pick a working model if user left model field blank
    if not model and discovered_models:
        model = discovered_models[0]
        to_save["AI_MODEL"] = model
        save_env_dict(to_save)
        add_log("AI_GATEWAY", f"Auto-discovered {len(discovered_models)} models; defaulting to '{model}'.")

    # Step 2: Live micro-inference test for each distinct model
    models_to_test = []
    main_model_id = model or (discovered_models[0] if discovered_models else (PROVIDER_PRESETS[provider].get("default_model") or "default"))
    models_to_test.append(("Main Model", main_model_id))

    if model_scoring and model_scoring != main_model_id:
        models_to_test.append(("Scoring Model", model_scoring))
    elif model_scoring:
        models_to_test.append(("Scoring Model (Alias)", model_scoring))

    if model_drafts and model_drafts not in [main_model_id, model_scoring]:
        models_to_test.append(("Drafts Model", model_drafts))
    elif model_drafts:
        models_to_test.append(("Drafts Model (Alias)", model_drafts))

    reports = []
    for purpose, m_id in models_to_test:
        rep = _run_micro_inference(base_url, api_key, m_id, purpose)
        reports.append(rep)
        status_sym = "✅" if rep["status"] == "ok" else "❌"
        add_log("AI_GATEWAY", f"Model [{purpose}: {m_id}] {status_sym} {rep['latency_ms']}ms - {rep['reply'] or rep['error']}")

    ok_count = sum(1 for r in reports if r["status"] == "ok")
    overall_status = "success" if ok_count == len(reports) else ("partial" if ok_count > 0 else "error")

    if overall_status == "error":
        err_msg = reports[0]["error"] if reports else "Inference test failed"
        raise HTTPException(status_code=400, detail=f"Model error: {err_msg}")

    return {
        "status": "success",
        "overall_status": overall_status,
        "message": f"Verified {ok_count}/{len(reports)} models responsive via {PROVIDER_PRESETS[provider]['label']}.",
        "gateway_reachable": gateway_reachable,
        "models": reports,
        "discovered_models": discovered_models,
        "active_model": main_model_id
    }

@app.post("/api/test-ai-prompt")
def test_ai_prompt(payload: TestPromptRequest):
    """Interactive Sandbox: sends a user's custom test prompt to a chosen model."""
    import requests
    import time
    from src.ai.providers import PROVIDER_PRESETS
    env = load_env_dict()
    provider = (payload.provider or env.get("AI_PROVIDER") or "custom").strip().lower()
    preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS.get("custom", {}))

    base_url = (payload.baseUrl or env.get("AI_BASE_URL") or env.get("OMNIROUTE_BASE_URL") or preset.get("base_url", "")).strip()
    api_key = (payload.apiKey or "").strip()
    if is_masked_secret(api_key) or not api_key:
        api_key = (env.get("AI_API_KEY") or env.get("OMNIROUTE_API_KEY") or "").strip()

    raw_model = (payload.model_id or "").strip()
    if not raw_model or raw_model.lower() in ["main", "default", "auto", "scoring", "drafts"]:
        if raw_model.lower() == "scoring":
            raw_model = env.get("AI_MODEL_SCORING") or ""
        elif raw_model.lower() == "drafts":
            raw_model = env.get("AI_MODEL_DRAFTS") or ""
        if not raw_model or raw_model.lower() in ["main", "default", "auto"]:
            raw_model = env.get("AI_MODEL") or env.get("CLAUDE_MODEL") or preset.get("default_model", "gpt-4o-mini")
    model_id = raw_model.strip()

    if not base_url:
        raise HTTPException(status_code=400, detail="Base URL is missing. Configure it in settings.")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    prompt_body = payload.prompt.strip()
    if not prompt_body:
        raise HTTPException(status_code=400, detail="Prompt text cannot be empty.")

    chat_payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt_body}],
        "max_tokens": 300,
        "temperature": payload.temperature or 0.7
    }

    started = time.time()
    try:
        url = f"{base_url.rstrip('/')}/chat/completions"
        resp = requests.post(url, headers=headers, json=chat_payload, timeout=20)
        elapsed_ms = int((time.time() - started) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            reply_text = ""
            if choices and "message" in choices[0]:
                reply_text = choices[0]["message"].get("content", "").strip()
            elif choices and "text" in choices[0]:
                reply_text = choices[0].get("text", "").strip()

            tokens = data.get("usage", {}).get("total_tokens", 0)
            return {
                "status": "success",
                "model_id": model_id,
                "reply": reply_text or "[Empty response received]",
                "latency_ms": elapsed_ms,
                "tokens": tokens,
                "error": None
            }
        else:
            err_msg = f"HTTP {resp.status_code}"
            try:
                err_data = resp.json()
                if "error" in err_data:
                    err_detail = err_data["error"]
                    err_msg = err_detail.get("message") if isinstance(err_detail, dict) else str(err_detail)
            except Exception:
                err_msg = resp.text[:200]
            return {
                "status": "error",
                "model_id": model_id,
                "reply": None,
                "latency_ms": elapsed_ms,
                "tokens": 0,
                "error": err_msg
            }
    except requests.exceptions.Timeout:
        elapsed_ms = int((time.time() - started) * 1000)
        return {
            "status": "error",
            "model_id": model_id,
            "reply": None,
            "latency_ms": elapsed_ms,
            "tokens": 0,
            "error": f"Request timed out after {elapsed_ms/1000:.1f}s. Model '{model_id}' at {base_url} took too long to reply. Ensure upstream credentials or network route for this model are active."
        }
    except Exception as e:
        elapsed_ms = int((time.time() - started) * 1000)
        return {
            "status": "error",
            "model_id": model_id,
            "reply": None,
            "latency_ms": elapsed_ms,
            "tokens": 0,
            "error": str(e)
        }


@app.get("/api/ai-meter")
def ai_meter():
    """Token/latency/cost meter for AI calls this process lifetime."""
    from src.ai.providers import get_ai_meter
    return get_ai_meter()


# -----------------------------------------------------------------------------
# Throttled auto-send outbox (single identity, one recipient per transaction)
# -----------------------------------------------------------------------------
def _send_config() -> Dict[str, Any]:
    env = load_env_dict()
    def _int(key: str, default: int) -> int:
        try:
            return max(1, int((env.get(key) or default)))
        except (TypeError, ValueError):
            return default
    return {
        "daily_cap": _int("AI_SEND_DAILY_CAP", 25),
        "interval_sec": _int("AI_SEND_INTERVAL_SEC", 240),
        "bcc_self": (env.get("AI_SEND_BCC_SELF", "true").strip().lower()
                     not in ("0", "false", "no", "off")),
    }


def _extract_emails(text: str):
    import re
    return re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")


class QueueMailRequest(BaseModel):
    app_id: int
    to_email: Optional[str] = None
    attach_resume: Optional[bool] = True
    resume_type: Optional[str] = None
    resume_filename: Optional[str] = None
    scheduled_at: Optional[str] = None


@app.post("/api/outreach/queue")
def queue_outreach_mail(req: QueueMailRequest):
    """Queue tailored mail(s) for throttled auto-send (supports multiple comma/semicolon recipients)."""
    app = db_mgr.get_application(req.app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if not (app.email_draft_subject and app.email_draft_body):
        raise HTTPException(status_code=400, detail="Generate the mail for this job first.")
    raw_to = (req.to_email or "").strip()
    if not raw_to:
        found = _extract_emails(app.contact_info)
        raw_to = found[0] if found else ""
    if not raw_to:
        raise HTTPException(status_code=400, detail="No recipient email — none found on this listing.")

    # Extract all valid emails from comma / semicolon separated input
    candidates = [c.strip() for c in re.split(r'[,;]+', raw_to) if c.strip()]
    unique_emails = []
    for cand_str in candidates:
        extracted = _extract_emails(cand_str)
        for em in extracted:
            if em not in unique_emails:
                unique_emails.append(em)

    if not unique_emails:
        raise HTTPException(status_code=400, detail="No valid email address found in input.")

    sched_dt = None
    if req.scheduled_at and req.scheduled_at.strip():
        try:
            clean_s = req.scheduled_at.strip().replace("Z", "")
            sched_dt = datetime.fromisoformat(clean_s)
        except Exception:
            sched_dt = None

    attachment = None
    if req.attach_resume:
        # Determine target resume: direct filename chosen by user, or application's resume_used, or user primary resume
        target_fn = req.resume_filename or getattr(app, "resume_used", None)
        if target_fn:
            target_fn = Path(target_fn).name
            cand_p = RESUMES_DIR / target_fn
            if cand_p.exists():
                attachment = str(cand_p)

        if not attachment:
            # Fallback to active resume for job title / profile primary resume
            active = _active_resume(preferred_filename=getattr(app, "resume_used", None), job_title=app.title)
            if active and (RESUMES_DIR / active[0]).exists():
                attachment = str(RESUMES_DIR / active[0])
            else:
                files = [f for f in RESUMES_DIR.glob("*.*") if f.suffix.lower() in (".md", ".txt", ".docx", ".pdf")]
                if files:
                    attachment = str(max(files, key=lambda f: f.stat().st_mtime))

    queued_ids = []
    for to_em in unique_emails:
        row_id = db_mgr.queue_email(app.id, to_em, app.email_draft_subject,
                                    app.email_draft_body, attachment,
                                    scheduled_at=sched_dt)
        queued_ids.append(row_id)

    _ensure_sender()
    queued = len(db_mgr.get_outbox(status="queued"))
    add_log("QUEUED", f"Mail queued for {app.company} → {', '.join(unique_emails)} (queue depth #{queued}).")
    return {
        "status": "queued",
        "outbox_ids": queued_ids,
        "outbox_id": queued_ids[0] if queued_ids else None,
        "position": queued,
        "to_email": unique_emails[0],
        "to_emails": unique_emails,
        "attachment": bool(attachment),
        "scheduled_at": sched_dt.strftime("%Y-%m-%d %H:%M") if sched_dt else "Immediately"
    }


@app.get("/api/outreach/queue")
def outbox_list(status: Optional[str] = None):
    """Inspect the send queue."""
    return db_mgr.get_outbox(status=status)


@app.post("/api/outreach/queue/toggle-pause")
def toggle_outbox_pause():
    global OUTBOX_PAUSED
    with OUTBOX_PAUSED_LOCK:
        OUTBOX_PAUSED = not OUTBOX_PAUSED
        is_paused = OUTBOX_PAUSED
    add_log("OUTBOX", f"Auto-send queue {'PAUSED' if is_paused else 'RESUMED'} by user.")
    return {"status": "paused" if is_paused else "resumed", "paused": is_paused}


@app.get("/api/outreach/queue/status")
def outbox_status():
    with OUTBOX_PAUSED_LOCK:
        is_paused = OUTBOX_PAUSED
    return {"paused": is_paused}


@app.post("/api/outreach/queue/clear")
def clear_outbox_queue_route():
    count = db_mgr.clear_outbox_queue()
    add_log("OUTBOX", f"Cleared {count} pending email(s) from outbox queue.")
    return {"status": "cleared", "count": count}


@app.get("/api/outreach/sent")
def outbox_sent_list(limit: int = 50):
    return db_mgr.get_sent_outbox(limit=limit)


def _norm_dt(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return None
    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _period_cutoff(period: str):
    """Datetime lower bound for analytics periods (None = all time). Returns naive UTC datetime."""
    p = (period or "30d").lower()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if p == "90d":
        return now - timedelta(days=90)
    if p == "ytd":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if p in ("all", "custom"):
        return None
    return now - timedelta(days=30)


@app.get("/api/analytics")
def analytics(period: str = Query("30d", description="30d, 90d, ytd or all")):
    """Live analytics: pipeline counts, averages, adaptive trends, and all outreach rows."""
    cutoff = _period_cutoff(period)
    apps = db_mgr.get_all_applications()
    if cutoff:
        apps = [a for a in apps if not a.created_at or (_norm_dt(a.created_at) and _norm_dt(a.created_at) >= cutoff)]
    by_status: Dict[str, int] = {}
    scores, ats_scores = [], []
    for a in apps:
        by_status[a.status or "Scraped"] = by_status.get(a.status or "Scraped", 0) + 1
        if (a.match_score or 0) > 0:
            scores.append(a.match_score)
        if getattr(a, "ats_score", None):
            ats_scores.append(a.ats_score)
    sent_rows = db_mgr.get_outbox(status="sent")
    queued_rows = db_mgr.get_outbox(status="queued")
    if cutoff:
        def _in(row):
            try:
                raw_ts = row.get("sent_at") or row.get("scheduled_at") or ""
                ts = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M")
                return ts >= cutoff
            except (TypeError, ValueError):
                return True
        sent_rows = [r for r in sent_rows if _in(r)]
    applied_count = len([a for a in apps if (a.status or "").lower() == "applied"])
    outbox_rows = db_mgr.get_outbox(limit=500)
    app_by_id = {a.id: a for a in apps}
    outbox_app_ids = set()
    combined_recent = []
    for r in outbox_rows:
        aid = r.get("app_id")
        if aid:
            outbox_app_ids.add(aid)
        a = app_by_id.get(aid)
        combined_recent.append({
            "to_email": r.get("to_email", "") or (a.contact_info if a else "") or "Direct Email",
            "company": (a.company if a else ""),
            "title": (a.title if a else ""),
            "match_score": int(a.match_score) if a and a.match_score else 0,
            "status": r.get("status", "") or (a.status if a else ""),
            "sent_at": r.get("sent_at") or r.get("scheduled_at") or (a.updated_at.strftime("%Y-%m-%d %H:%M") if a and a.updated_at else ""),
            "link": (a.link if a else "") or (a.author_profile_url if a else ""),
            "app_id": aid
        })

    # Also include any applications marked as "Applied" or other progression statuses not in outbox
    other_apps = [a for a in apps if a.id not in outbox_app_ids and (a.status or "").lower() in ("applied", "interviewing", "offer", "rejected", "archived")]
    for a in other_apps:
        contact = a.contact_info or (f"LinkedIn ({a.author_name})" if a.author_name else "LinkedIn Easy Apply")
        applied_time = a.updated_at or a.created_at
        time_str = applied_time.strftime("%Y-%m-%d %H:%M") if applied_time else ""
        combined_recent.append({
            "to_email": contact,
            "company": a.company or "",
            "title": a.title or "",
            "match_score": int(a.match_score) if a.match_score else 0,
            "status": a.status or "Applied",
            "sent_at": time_str,
            "link": a.link or a.author_profile_url or "",
            "app_id": a.id
        })

    def _recent_sort(item):
        return item.get("sent_at") or ""
    combined_recent.sort(key=_recent_sort, reverse=True)
    recent_rows = combined_recent

    qualified_count = len([s for s in scores if s >= 70])
    from datetime import date, timedelta
    today = date.today()
    daily_trend = []

    p_lower = (period or "30d").lower()
    if p_lower == "90d":
        trend_label = "Last 90 Days Velocity (Weekly)"
        for i in range(11, -1, -1):
            w_start = today - timedelta(days=(i * 7) + 6)
            w_end = today - timedelta(days=i * 7)
            w_label = f"W{12 - i}"

            def _in_week(created, s=w_start, e=w_end):
                if not created:
                    return False
                dt = created.date() if hasattr(created, "date") else None
                return dt is not None and s <= dt <= e

            w_apps = [a for a in apps if _in_week(a.created_at)]
            w_scores = [a.match_score for a in w_apps if (a.match_score or 0) > 0]
            daily_trend.append({
                "date": w_end.strftime("%Y-%m-%d"),
                "label": w_label,
                "count": len(w_apps),
                "avg_score": round(sum(w_scores) / len(w_scores)) if w_scores else 0
            })
    elif p_lower in ("ytd", "all"):
        trend_label = "Year-to-Date Velocity (Monthly)" if p_lower == "ytd" else "All-Time Velocity Trend"
        for i in range(5, -1, -1):
            m_target = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
            m_str = m_target.strftime("%Y-%m")
            m_label = m_target.strftime("%b")

            def _in_month(created, target=m_str):
                if not created:
                    return False
                if isinstance(created, str):
                    return created.startswith(target)
                try:
                    return created.strftime("%Y-%m") == target
                except Exception:
                    return False

            m_apps = [a for a in apps if _in_month(a.created_at)]
            m_scores = [a.match_score for a in m_apps if (a.match_score or 0) > 0]
            daily_trend.append({
                "date": m_str,
                "label": m_label,
                "count": len(m_apps),
                "avg_score": round(sum(m_scores) / len(m_scores)) if m_scores else 0
            })
    else:
        trend_label = "Last 14 Days Activity"
        for i in range(13, -1, -1):
            day_date = today - timedelta(days=i)
            day_str = day_date.strftime("%Y-%m-%d")

            def _matches_day(created, target_str=day_str):
                if not created:
                    return False
                if isinstance(created, str):
                    return created.startswith(target_str)
                try:
                    return created.strftime("%Y-%m-%d") == target_str
                except Exception:
                    return False

            day_apps = [a for a in apps if _matches_day(a.created_at)]
            day_scores = [a.match_score for a in day_apps if (a.match_score or 0) > 0]
            daily_trend.append({
                "date": day_str,
                "label": day_date.strftime("%a"),
                "count": len(day_apps),
                "avg_score": round(sum(day_scores) / len(day_scores)) if day_scores else 0
            })

    return {
        "period": period,
        "trend_label": trend_label,
        "total": len(apps),
        "by_status": by_status,
        "avg_match": round(sum(scores) / len(scores)) if scores else 0,
        "avg_ats": round(sum(ats_scores) / len(ats_scores)) if ats_scores else 0,
        "scored": len(scores),
        "qualified": qualified_count,
        "sent": len(sent_rows),
        "applied": applied_count,
        "queued": len(queued_rows),
        "daily_trend": daily_trend,
        "recent": recent_rows,
    }


@app.get("/api/analytics/export")
def export_analytics_csv():
    """Download full applications pipeline as a structured CSV spreadsheet."""
    apps = db_mgr.get_all_applications()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Job ID", "Position", "Company", "Location", "Recruiter", "Contact Email", "Match Score", "ATS Score", "Status", "Created At", "Updated At", "Post URL"])
    for a in apps:
        writer.writerow([
            a.id,
            a.job_id or "",
            a.title or "",
            a.company or "",
            a.location or "",
            a.author_name or "",
            a.contact_info or "",
            a.match_score or 0,
            getattr(a, "ats_score", 0) or 0,
            a.status or "Scraped",
            a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
            a.updated_at.strftime("%Y-%m-%d %H:%M:%S") if a.updated_at else "",
            a.link or a.author_profile_url or ""
        ])
    csv_bytes = output.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=easiapply_applications_pipeline.csv"}
    )


class ApplicationStatusUpdate(BaseModel):
    status: str


@app.patch("/api/applications/{app_id}/status")
def update_application_status(app_id: str, payload: ApplicationStatusUpdate):
    """Lifecycle stage updater: Applied -> Interviewing -> Offer / Rejected / Archived."""
    status_clean = payload.status.strip()
    if not status_clean:
        raise HTTPException(status_code=400, detail="Status cannot be empty.")
    try:
        int_id = int(app_id)
        db_mgr.update_application(int_id, status=status_clean)
    except (ValueError, TypeError):
        session = db_mgr.get_session()
        try:
            from src.storage.models import JobApplication
            app_obj = session.query(JobApplication).filter((JobApplication.job_id == app_id) | (JobApplication.id == app_id)).first()
            if app_obj:
                app_obj.status = status_clean
                session.commit()
            else:
                raise HTTPException(status_code=404, detail="Application not found")
        finally:
            session.close()
    add_log("STATUS", f"Application #{app_id} marked as '{status_clean}'.")
    return {"status": "success", "app_id": app_id, "new_status": status_clean}


@app.post("/api/settings/prompts/reset")
def reset_prompts():
    """Restore default AI heuristics & system prompts."""
    defaults = {
        "SYSTEM_PROMPT_EXTRACTION": (
            "You are an expert HR data parsing engine. Extract the structured fields strictly according to schema: "
            "Job Title, Company Name, Recruiter/Hiring Manager Name, Recruiter Direct Contact Email, Job Location, Seniority Level, "
            "and Clean Plaintext Description without LinkedIn interface noise."
        ),
        "SYSTEM_PROMPT_SCORING": (
            "As an expert ATS auditor and career coach:\n"
            "1. Rate the alignment between my authentic experience and the requirements in the job description (0-100%).\n"
            "2. Provide concise reasoning (2-3 sentences). Mention any crucial skill-keywords or qualifications that are missing from my resume but required for the job."
        ),
        "SYSTEM_PROMPT_EMAIL": (
            "You have three goals:\n"
            "1. Draft a Tailored Professional Email (Under 200 words, direct hook, clear CTA).\n"
            "2. Suggest 3-4 bullet-point improvements to my resume to align closely with this opening, along with missing keywords.\n"
            "3. Draft a warm, compelling LinkedIn Connection Note under 280 characters."
        ),
    }
    save_env_dict(defaults)
    add_log("SETTINGS", "Restored default AI prompts and directives.")
    return {"status": "success", "message": "Default prompts restored successfully.", "prompts": defaults}


@app.post("/api/outreach/cancel/{row_id}")
def outbox_cancel(row_id: int):
    """Cancel a queued mail before it sends."""
    db_mgr.mark_outbox(row_id, status="cancelled")
    add_log("CANCELLED", f"Queued mail #{row_id} cancelled.")
    return {"status": "cancelled", "outbox_id": row_id}


_SENDER_THREAD = None
_SENDER_LOCK = threading.Lock()
OUTBOX_PAUSED = False
OUTBOX_PAUSED_LOCK = threading.Lock()


def _ensure_sender():
    global _SENDER_THREAD
    with _SENDER_LOCK:
        if _SENDER_THREAD and _SENDER_THREAD.is_alive():
            return
        _SENDER_THREAD = threading.Thread(target=_sender_loop, daemon=True)
        _SENDER_THREAD.start()


def _sender_loop():
    """Trickle loop: max one send per interval, daily cap, backoff on deferral."""
    import random
    while True:
        try:
            time.sleep(10)
            with OUTBOX_PAUSED_LOCK:
                if OUTBOX_PAUSED:
                    continue
            cfg = _send_config()
            if db_mgr.count_sent_today() >= cfg["daily_cap"]:
                continue  # roll over to next day automatically
            last = db_mgr.last_sent_at()
            if last:
                # Handle both offset-naive and offset-aware datetimes safely
                now_utc = _utc_now()
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (now_utc - last).total_seconds()
                jitter = random.uniform(0, cfg["interval_sec"] * 0.25)
                if elapsed < cfg["interval_sec"] + jitter:
                    continue
            due = db_mgr.get_due_outbox(limit=1)
            if not due:
                continue
            item = due[0]
            db_mgr.mark_outbox(item["id"], status="sending")
            try:
                from src.mail.smtp_client import EmailClient
                mailer = EmailClient()
                if not mailer.enabled:
                    raise RuntimeError("SMTP credentials not configured in Settings.")
                env = load_env_dict()
                bcc = [env.get("SENDER_EMAIL") or mailer.smtp_user] if cfg["bcc_self"] else None
                ok = mailer.send(
                    item["to_email"], item["subject"], item["body"],
                    attachment_path=item["attachment_path"],
                    bcc_emails=bcc)
                if not ok:
                    raise RuntimeError("SMTP send returned failure.")
            except Exception as e:
                msg = str(e)
                attempts = (item["attempts"] or 0) + 1
                transient = any(code in msg for code in ("421", "452", "4.7.", "try again", "timeout", "timed out"))
                if transient and attempts < 5:
                    backoff_min = 2 ** attempts
                    db_mgr.mark_outbox(
                        item["id"], status="queued", attempts=attempts, error=msg,
                        scheduled_at=_utc_now() + timedelta(minutes=backoff_min))
                    add_log("WARN_SEND", f"Deferral for {item['to_email']} — backing off {backoff_min}m (attempt {attempts}).")
                else:
                    db_mgr.mark_outbox(item["id"], status="failed", attempts=attempts, error=msg)
                    add_log("ERR_SEND", f"Send failed for {item['to_email']}: {msg[:160]}")
                continue
            db_mgr.mark_outbox(item["id"], status="sent", sent_at=_utc_now(), error="")
            db_mgr.update_application(item["app_id"], status="Applied")
            add_log("SENT", f"Mail sent to {item['to_email']}.")
        except Exception as e:
            add_log("ERR_SEND", f"Sender loop error: {str(e)[:160]}")


@app.post("/api/error")
def report_error(report: ErrorReport):
    """Log a client-side failure so it shows up in the activity console."""
    add_log("ERR_UI", f"[{report.section}] {report.message}")
    return {"status": "logged", "section": report.section}


SESSION_FILE = BASE_DIR / "data" / "linkedin_session.json"

def _read_linkedin_session():
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def _write_linkedin_session(data: dict):
    try:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving linkedin session: {e}")


def _get_linkedin_login_credential(user_data_dir: Path):
    """Attempt to find the login email or phone number used for LinkedIn."""
    default_dir = user_data_dir / "Default"
    # 1. Check Chrome Login Data sqlite
    login_db = default_dir / "Login Data"
    if login_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{login_db}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT username_value FROM logins WHERE origin_url LIKE '%linkedin%' AND username_value != '' ORDER BY date_created DESC LIMIT 1")
            row = cur.fetchone()
            conn.close()
            if row and row[0]:
                return row[0].strip()
        except Exception:
            pass

    # 2. Check Chrome Web Data (autofill session_key)
    web_db = default_dir / "Web Data"
    if web_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{web_db}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT value FROM autofill WHERE name = 'session_key' AND value != '' ORDER BY date_created DESC LIMIT 1")
            row = cur.fetchone()
            conn.close()
            if row and row[0]:
                return row[0].strip()
        except Exception:
            pass

    # 3. Check saved session JSON
    session_data = _read_linkedin_session()
    if session_data and session_data.get("login_credential"):
        return session_data["login_credential"].strip()

    # 4. Check user settings LINKEDIN_EMAIL
    try:
        from src.storage.db import db_mgr
        settings = db_mgr.get_settings()
        if settings and settings.get("LINKEDIN_EMAIL"):
            return settings["LINKEDIN_EMAIL"].strip()
    except Exception:
        pass

    return None


@app.get("/api/linkedin-status")
def linkedin_status():
    """Authoritative LinkedIn connection status with logged-in account name and credential."""
    user_data = Path(os.getenv("USER_DATA_DIR", str(BASE_DIR / "user_data")))
    default_dir = user_data / "Default"
    
    session_data = _read_linkedin_session()

    # Check for actual LinkedIn cookies in Cookies SQLite
    cookie_paths = [
        default_dir / "Network" / "Cookies",
        default_dir / "Cookies"
    ]
    has_li_cookie = False
    for cp in cookie_paths:
        if cp.exists() and cp.stat().st_size > 0:
            try:
                import sqlite3
                conn = sqlite3.connect(f"file:{cp.resolve()}?mode=ro", uri=True)
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM cookies WHERE (host_key LIKE '%linkedin.com%' OR host_key LIKE '%.linkedin.com') AND name = 'li_at' LIMIT 1")
                if cur.fetchone():
                    has_li_cookie = True
                conn.close()
            except Exception:
                # If locked by open Chrome instance on Windows, read a temporary shadow copy
                try:
                    import tempfile, shutil, sqlite3
                    tmp_cp = Path(tempfile.gettempdir()) / f"tmp_cookies_{os.getpid()}.db"
                    shutil.copy2(cp, tmp_cp)
                    conn = sqlite3.connect(str(tmp_cp))
                    cur = conn.cursor()
                    cur.execute("SELECT 1 FROM cookies WHERE (host_key LIKE '%linkedin.com%' OR host_key LIKE '%.linkedin.com') AND name = 'li_at' LIMIT 1")
                    if cur.fetchone():
                        has_li_cookie = True
                    conn.close()
                    try:
                        tmp_cp.unlink(missing_ok=True)
                    except Exception:
                        pass
                except Exception:
                    pass
            if has_li_cookie:
                break
    
    is_logged_in = has_li_cookie or (session_data and bool(session_data.get("logged_in")))

    if is_logged_in:
        # Auto-heal session JSON file if cookie was verified
        if not session_data or not session_data.get("logged_in"):
            session_data = {
                "logged_in": True,
                "account_name": (session_data and session_data.get("account_name")) or "LinkedIn Member",
                "profile_url": (session_data and session_data.get("profile_url")) or "",
                "updated_at": datetime.now().isoformat()
            }
            _write_linkedin_session(session_data)

        raw_name = session_data.get("account_name") if session_data else None
        account_name = raw_name.split("\n")[0].strip() if raw_name else "LinkedIn Member"
        login_credential = _get_linkedin_login_credential(user_data)
        profile_url = session_data.get("profile_url") if session_data else None
        return {
            "status": "connected",
            "logged_in": True,
            "account_name": account_name,
            "login_credential": login_credential,
            "profile_url": profile_url,
            "user_data_dir": str(user_data),
            "has_profile": True,
            "has_cookies": True,
            "message": f"Connected as {account_name}"
        }
    else:
        return {
            "status": "disconnected",
            "logged_in": False,
            "account_name": None,
            "login_credential": None,
            "profile_url": None,
            "user_data_dir": str(user_data),
            "has_profile": default_dir.exists(),
            "has_cookies": False,
            "message": "Not connected. Log in via Chrome session."
        }


@app.post("/api/linkedin/login-window")
def open_linkedin_login_window(background_tasks: BackgroundTasks):
    """Launch a visible, maximized Chrome window directly to LinkedIn for interactive login."""
    try:
        add_log("AUTH", "Launching visible Chrome window for LinkedIn authentication...")
        
        # Reset any previous explicit logout state so polling detects active auth
        _write_linkedin_session({
            "logged_in": None,
            "account_name": None,
            "login_credential": None,
            "profile_url": None,
            "updated_at": datetime.now().isoformat()
        })

        def _interactive_worker():
            bm = None
            try:
                from src.browser.engine import BrowserManager
                user_data = os.getenv("USER_DATA_DIR", str(BASE_DIR / "user_data"))
                bm = BrowserManager()
                bm.user_data_dir = user_data
                bm.headless = False
                bm.start()
                page = bm.new_page()
                page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=45000)
                add_log("AUTH", "Visible Chrome window opened. Please complete LinkedIn login...")

                # Poll every 1.5 seconds for up to 5 minutes (200 * 1.5s)
                for _ in range(200):
                    time.sleep(1.5)
                    try:
                        if not bm.browser or not bm.browser.pages:
                            break
                        
                        # 1. Real-time In-Memory Cookie Check via CDP (fastest, most reliable)
                        has_li_cookie = False
                        try:
                            cookies = bm.browser.cookies()
                            has_li_cookie = any(c.get("name") == "li_at" and bool(c.get("value")) for c in cookies)
                        except Exception:
                            pass

                        # 2. Check all open browser tabs for logged-in indicators
                        is_logged_in = has_li_cookie
                        active_page = page
                        for p in bm.browser.pages:
                            try:
                                if p.is_closed():
                                    continue
                                u = p.url.lower()
                                if any(k in u for k in ("feed", "mynetwork", "jobs", "/in/", "messaging", "notifications", "search/results")):
                                    is_logged_in = True
                                    active_page = p
                                    break
                                # Check navigation bar or avatar in DOM
                                if p.query_selector("#global-nav, .global-nav, nav.global-nav, .feed-identity-module, .global-nav__me"):
                                    is_logged_in = True
                                    active_page = p
                                    break
                            except Exception:
                                pass

                        if is_logged_in:
                            name = None
                            profile_url = None
                            try:
                                info = active_page.evaluate('''() => {
                                    const nameEl = document.querySelector('.feed-identity-module__actor-meta a, .global-nav__me .t-bold, .profile-rail-card__actor-link, [data-control-name="identity_welcome_message"]');
                                    const inLinks = Array.from(document.querySelectorAll('a[href*="/in/"]')).map(a => ({ text: a.innerText.trim(), href: a.href }));
                                    const pLink = inLinks.find(l => l.text && !l.text.toLowerCase().includes('follow') && !l.text.toLowerCase().includes('connect') && !l.text.toLowerCase().includes('learning')) || inLinks[0];
                                    return {
                                        name: (nameEl ? nameEl.innerText.trim() : (pLink ? pLink.text : null)),
                                        url: pLink ? pLink.href : null
                                    };
                                }''')
                                if info:
                                    name = (info.get("name") or "").split("\n")[0].strip() or None
                                    profile_url = info.get("url") or None
                            except Exception:
                                pass

                            _write_linkedin_session({
                                "logged_in": True,
                                "account_name": name or "LinkedIn Member",
                                "profile_url": profile_url or "",
                                "updated_at": datetime.now().isoformat()
                            })
                            add_log("AUTH", f"LinkedIn session verified for: {name or 'LinkedIn Member'}")
                            time.sleep(1.5)
                            break
                    except Exception:
                        # Continue polling; do not break on temporary navigation events
                        continue
            except Exception as ex:
                add_log("ERR_AUTH", f"Interactive login error: {str(ex)}")
            finally:
                if bm:
                    try:
                        bm.stop()
                    except Exception:
                        pass
                
        background_tasks.add_task(_interactive_worker)
        return {"status": "started", "message": "Chrome window launched for LinkedIn authentication."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reset-apps")
def reset_applications():
    """Clear Job Data: deletes applications, outbox records, resumes, and tailored CVs."""
    try:
        session = db_mgr.get_session()
        from src.storage.models import JobApplication, OutboxEmail
        session.query(JobApplication).delete()
        session.query(OutboxEmail).delete()
        session.commit()
        session.close()

        # Clear resumes
        if RESUMES_DIR.exists():
            shutil.rmtree(RESUMES_DIR, ignore_errors=True)
            RESUMES_DIR.mkdir(parents=True, exist_ok=True)

        # Clear tailored resumes
        tailored_dir = BASE_DIR / "data" / "tailored"
        if tailored_dir.exists():
            shutil.rmtree(tailored_dir, ignore_errors=True)
            tailored_dir.mkdir(parents=True, exist_ok=True)

        # Clear scraped jobs JSON cache
        scraped_cache = BASE_DIR / "data" / "scraped_jobs.json"
        if scraped_cache.exists():
            try:
                scraped_cache.unlink()
            except Exception:
                pass

        add_log("PURGE", "Job data cleared (applications, outbox, resumes & tailored CVs removed).")
        return {"status": "purged", "message": "Job data cleared successfully."}
    except Exception as e:
        add_log("ERR_PURGE", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset-all")
def reset_workspace():
    """Factory Reset: wipes everything — applications, outbox, resumes, tailored CVs, API keys, mail config, LinkedIn session."""
    try:
        # Clear applications and outbox table
        session = db_mgr.get_session()
        from src.storage.models import JobApplication, OutboxEmail
        session.query(JobApplication).delete()
        session.query(OutboxEmail).delete()
        session.commit()
        session.close()

        # Clear resumes
        if RESUMES_DIR.exists():
            shutil.rmtree(RESUMES_DIR, ignore_errors=True)
            RESUMES_DIR.mkdir(parents=True, exist_ok=True)

        # Clear tailored resumes
        tailored_dir = BASE_DIR / "data" / "tailored"
        if tailored_dir.exists():
            shutil.rmtree(tailored_dir, ignore_errors=True)
            tailored_dir.mkdir(parents=True, exist_ok=True)

        # Clear scraped jobs JSON cache
        scraped_cache = BASE_DIR / "data" / "scraped_jobs.json"
        if scraped_cache.exists():
            try:
                scraped_cache.unlink()
            except Exception:
                pass

        # Wipe .env file to clean default template
        clean_env_template = (
            "# --- Browser Automation Settings ---\n"
            "HEADLESS=False\n"
            "USER_DATA_DIR=\"./user_data\"\n"
            "SLOW_MO_MS=100\n\n"
            "# --- Safety Limits ---\n"
            "MAX_JOBS_PER_SESSION=25\n"
            "MIN_PAGE_DELAY=3\n"
            "MAX_PAGE_DELAY=8\n\n"
            "# --- Search Defaults ---\n"
            "DEFAULT_KEYWORDS=\"\"\n"
            "DEFAULT_LOCATION=\"Remote\"\n\n"
            "# --- AI Provider Settings ---\n"
            "AI_PROVIDER=\"custom\"\n"
            "AI_BASE_URL=\"\"\n"
            "AI_API_KEY=\"\"\n"
            "AI_MODEL=\"\"\n"
            "AI_MODEL_SCORING=\"\"\n"
            "AI_MODEL_DRAFTS=\"\"\n\n"
            "# --- Email (SMTP) Settings ---\n"
            "SMTP_HOST=\"\"\n"
            "SMTP_PORT=587\n"
            "SMTP_USER=\"\"\n"
            "SMTP_PASSWORD=\"\"\n"
            "SENDER_NAME=\"\"\n"
            "SENDER_EMAIL=\"\"\n"
        )
        if ENV_PATH.exists():
            ENV_PATH.write_text(clean_env_template, encoding="utf-8")

        # Clear stray databases
        for extra_db in [BASE_DIR / "data" / "easiapply.db", BASE_DIR / "data" / "test_cascade_apps.db"]:
            if extra_db.exists():
                try:
                    extra_db.unlink()
                except Exception:
                    pass

        # Clear saved user target profile criteria
        if PROFILE_PREFS_PATH.exists():
            try:
                PROFILE_PREFS_PATH.unlink()
            except Exception:
                pass

        # Clear in-memory environment variables
        for k in list(os.environ.keys()):
            if k.startswith(("AI_", "OMNIROUTE_", "CLAUDE_", "OPENAI_", "OPENROUTER_", "SMTP_", "SENDER_", "LINKEDIN_")):
                os.environ.pop(k, None)

        # Clear LinkedIn session file & record explicit logout
        _write_linkedin_session({"logged_in": False, "account_name": None, "login_credential": None, "profile_url": None})

        # Clear LinkedIn cookies from user_data
        user_data = Path(os.getenv("USER_DATA_DIR", str(BASE_DIR / "user_data")))
        for cookie_path in [
            user_data / "Default" / "Network" / "Cookies",
            user_data / "Default" / "Cookies"
        ]:
            if cookie_path.exists():
                try:
                    import sqlite3
                    conn = sqlite3.connect(str(cookie_path))
                    conn.execute("DELETE FROM cookies WHERE host_key LIKE '%linkedin%'")
                    conn.commit()
                    conn.close()
                except Exception:
                    try:
                        cookie_path.unlink()
                    except Exception:
                        pass

        # Clear activity logs
        global ACTIVITY_LOGS
        with LOG_LOCK:
            ACTIVITY_LOGS.clear()

        add_log("PURGE", "Factory reset complete — all applications, analytics, credentials, and sessions wiped.")
        return {"status": "purged", "message": "Factory reset complete."}
    except Exception as e:
        add_log("ERR_PURGE", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset-data")
def reset_application_data():
    """Reset Application Data: clears applications, outbox, cached scraped data, and telemetry logs.
    Preserves resumes, settings, and API keys as promised by the UI modal."""
    try:
        # 1. Clear database applications & outbox
        db_mgr.clear_all_applications()

        # 2. Clear tailored resumes
        tailored_dir = BASE_DIR / "data" / "tailored"
        if tailored_dir.exists():
            shutil.rmtree(tailored_dir, ignore_errors=True)
            tailored_dir.mkdir(parents=True, exist_ok=True)

        # 3. Clear scraped jobs cache
        scraped_cache = BASE_DIR / "data" / "scraped_jobs.json"
        if scraped_cache.exists():
            try:
                scraped_cache.unlink()
            except Exception:
                pass

        # 4. Clear activity logs
        global ACTIVITY_LOGS
        with LOG_LOCK:
            ACTIVITY_LOGS.clear()

        add_log("PURGE", "Application data reset complete — applications, cache, and telemetry cleared (resumes and settings preserved).")
        return {"status": "purged", "message": "Application data reset successfully. Resumes and settings preserved."}
    except Exception as e:
        add_log("ERR_PURGE", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export-data")
def export_workspace_data():
    """Export workspace settings, resume metadata, and all scraped applications as a downloadable JSON backup."""
    try:
        settings_dict = load_env_dict()
        apps = db_mgr.get_all_applications()
        meta = get_resume_meta()
        payload = {
            "exported_at": datetime.now().isoformat(),
            "version": "2.4.0",
            "settings": get_masked_settings(),
            "resume_meta": meta,
            "application_count": len(apps),
            "applications": apps,
        }
        content = json.dumps(payload, indent=2, default=str)
        filename = f"easiapply_workspace_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        add_log("ERR_EXPORT", f"Failed to export data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/shutdown")
def shutdown_application():
    """Cleanly terminates the local backend server process."""
    add_log("SYS", "User requested application shutdown. Terminating background server process...")
    def _graceful_stop():
        time.sleep(0.4)
        try:
            # Terminate current process cleanly on Windows / POSIX
            os.kill(os.getpid(), signal.SIGTERM if hasattr(signal, "SIGTERM") else signal.SIGINT)
        except Exception:
            sys.exit(0)
    threading.Thread(target=_graceful_stop, daemon=True).start()
    return {"status": "shutting_down", "message": "Server stopped. You can safely close this browser tab."}


