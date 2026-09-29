"""Free (no-AI) ATS employability scoring.

Keyword coverage, title fit, seniority fit, and resume-format checks.
Runs inside the scoring worker so every scored row carries an explanation.
"""
import re
from typing import Dict, Any, List

_STOPWORDS = set(
    "and or the a an to of in for on with we you our are is be as at by from "
    "will this that it its into your their his her them they he she we us "
    "all any each more most other some such no nor not only own same so than "
    "too very can justery should now hiring join team role looking seek seeking "
    "must have has had ideal bonus perks apply opportunity opportunities who "
    "what when where why how plus including include across within per day today".split())

SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "staff", "lead", "principal"]


def _tokens(text: str) -> List[str]:
    raw = re.findall(r"[a-z][a-z0-9+#.\-]*", (text or "").lower())
    out = []
    for t in raw:
        t = t.strip(".-")
        if t and t not in _STOPWORDS and len(t) > 1:
            out.append(t)
    return out


def _top_terms(text: str, limit: int = 25) -> List[str]:
    freq: Dict[str, int] = {}
    for t in _tokens(text):
        freq[t] = freq.get(t, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:limit]]


def _years(text: str) -> int:
    found = [int(n) for n in re.findall(r"(\d{1,2})\s*\+?\s*years?", (text or "").lower())]
    return max(found) if found else 0


def _level(text: str) -> int:
    low = (text or "").lower()
    for i in range(len(SENIORITY_ORDER) - 1, -1, -1):
        if SENIORITY_ORDER[i] in low:
            return i
    return -1


def score_ats(resume_text: str, job_title: str, job_description: str) -> Dict[str, Any]:
    """Return {ats_score, breakdown{subscores, missing_keywords}} — pure python."""
    jd_terms = _top_terms(job_description)
    resume_set = set(_tokens(resume_text))
    resume_head = set(_tokens((resume_text or "")[:800]))

    # 1. keyword coverage (40%)
    hits = [t for t in jd_terms if t in resume_set]
    keyword = round(100 * len(hits) / max(1, len(jd_terms)))
    missing = [t for t in jd_terms if t not in resume_set][:10]

    # 2. title fit (25%)
    title_terms = _top_terms(job_title, limit=6)
    title_fit = round(100 * sum(1 for t in title_terms if t in resume_head)
                      / max(1, len(title_terms))) if title_terms else 50

    # 3. seniority fit (20%)
    jd_level, rs_level = _level(job_description), _level(resume_text)
    jd_years, rs_years = _years(job_description), _years(resume_text)
    seniority = 70  # neutral default when neither side states a level
    if jd_level >= 0 and rs_level >= 0:
        seniority = 100 if rs_level == jd_level else max(30, 100 - 25 * abs(rs_level - jd_level))
    elif jd_years and rs_years:
        seniority = 100 if rs_years >= jd_years else max(30, int(100 * rs_years / jd_years))

    # 4. format / contact hygiene (15%)
    checks = [
        bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", resume_text or "")),
        bool(re.search(r"experience|employment|work history", (resume_text or "").lower())),
        bool(re.search(r"education|skills", (resume_text or "").lower())),
        300 <= len((resume_text or "").split()) <= 2500,
    ]
    hygiene = round(100 * sum(checks) / len(checks))

    ats = round(0.40 * keyword + 0.25 * title_fit + 0.20 * seniority + 0.15 * hygiene)
    return {
        "ats_score": ats,
        "breakdown": {
            "keyword_coverage": keyword,
            "title_fit": title_fit,
            "seniority_fit": seniority,
            "format_hygiene": hygiene,
        },
        "missing_keywords": missing,
    }
