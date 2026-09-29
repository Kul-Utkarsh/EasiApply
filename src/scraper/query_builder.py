import os
import re
import urllib.parse
from typing import List, Tuple, Optional
from pydantic import BaseModel, Field

class LinkedInSearchStrategy(BaseModel):
    expanded_roles: List[str] = Field(default_factory=list, description="2-3 industry synonyms or related role titles")
    seniority_filters: List[str] = Field(default_factory=list, description="Seniority terms if requested, e.g. Senior, Lead")
    custom_exclusions: List[str] = Field(default_factory=list, description="Negative keywords to exclude, e.g. intern, junior")
    compiled_query: str = Field(..., description="The complete boolean search string for LinkedIn")


class LinkedInQueryBuilder:
    """
    Constructs high-precision LinkedIn search queries that target genuine hiring
    announcements while suppressing job-seeker posts, promotions, and noise.
    """

    UNIVERSAL_HIRING_TERMS = [
        '"we are hiring"',
        '"hiring"',
        '"join our team"',
        '"looking for a"'
    ]

    UNIVERSAL_EXCLUSIONS = [
        '"open to work"',
        '"#opentowork"',
        '"seeking new"',
        '"looking for my next"',
        '"hire me"'
    ]

    @classmethod
    def clean_role_query(cls, query_text: str) -> List[str]:
        """Splits comma/slash-separated role inputs and cleans whitespace."""
        raw = query_text.strip()
        # If user explicitly wrote boolean operators (AND / OR / NOT), respect their custom query
        if any(op in raw for op in [" AND ", " OR ", " NOT "]):
            return [raw]

        parts = re.split(r'[,|;/]+', raw)
        cleaned = []
        for p in parts:
            p_clean = p.strip()
            # Remove leading/trailing quotes if user typed them
            p_clean = p_clean.strip('"\'')
            # Filter out accidental hiring words if user typed "hiring product designer"
            p_clean = re.sub(r'(?i)\b(hiring|we are hiring|looking for)\b', '', p_clean).strip()
            if p_clean and len(p_clean) >= 2:
                cleaned.append(p_clean)
        return cleaned or [raw]

    @classmethod
    def extract_core_keywords(cls, query_text: str) -> List[str]:
        """
        Extracts lowercase stems and phrases used by the parser to verify
        that a post actually mentions the desired domain or role.
        """
        roles = cls.clean_role_query(query_text)
        keywords = set()
        for r in roles:
            r_lower = r.lower()
            keywords.add(r_lower)
            # Add significant words (len >= 4, excluding generic stopwords)
            stopwords = {"with", "from", "that", "this", "have", "role", "lead", "level", "senior", "junior"}
            words = [w for w in re.findall(r'[a-zA-Z]{3,}', r_lower) if w not in stopwords]
            keywords.update(words)
        return sorted(list(keywords), key=lambda x: len(x), reverse=True)

    @classmethod
    def build_deterministic_query(cls, query_text: str, location: str = "") -> str:
        """
        Builds a clean, native LinkedIn content search query.
        LinkedIn content search engine fails with 'No results found' if complex nested
        boolean expressions or NOT clauses are in the search bar.
        Candidate (#OpenToWork) and location filtering are handled with 100% precision
        locally by JobParser in Python.
        """
        clean_roles = cls.clean_role_query(query_text)

        # 1. Role Clause: "Product Designer" or ("Product Designer" OR "UX Designer")
        if len(clean_roles) == 1 and any(op in clean_roles[0] for op in [" AND ", " OR ", " NOT "]):
            roles_clause = clean_roles[0]
        else:
            quoted_roles = [f'"{r}"' if ' ' in r and not r.startswith('"') else r for r in clean_roles]
            if len(quoted_roles) > 1:
                roles_clause = f"({' OR '.join(quoted_roles)})"
            else:
                roles_clause = quoted_roles[0]
                if not roles_clause.startswith('"') and not roles_clause.startswith('('):
                    roles_clause = f'"{roles_clause}"'

        # 2. Native Hiring Intent (accepted by LinkedIn search bar without breaking)
        hiring_clause = '(hiring OR "we are hiring" OR "we\'re hiring")'

        return f"{roles_clause} {hiring_clause}".strip()

    @classmethod
    def expand_role_synonyms(cls, role: str) -> List[str]:
        """
        Returns natural industry synonyms and title variations for any profession
        (Design, Engineering, Product, Data, Marketing, QA, etc.).
        """
        r_clean = role.strip().strip('"\'')
        r_lower = r_clean.lower()
        synonyms = [r_clean]

        SYNONYM_MAP = {
            # Design / Creative
            "product designer": ["UI/UX Designer", "UX Designer", "Product Design", "Digital Product Designer"],
            "ui/ux designer": ["Product Designer", "UX Designer", "UI Designer", "User Experience Designer"],
            "ux designer": ["Product Designer", "UI/UX Designer", "UX Researcher", "Interaction Designer"],
            "ui designer": ["UI/UX Designer", "Visual Designer", "Product Designer"],
            "visual designer": ["UI Designer", "Brand Designer", "Graphic Designer"],
            # Engineering / Development
            "software engineer": ["Software Developer", "Full Stack Developer", "Backend Engineer", "Software Development Engineer"],
            "full stack developer": ["Full Stack Engineer", "Software Engineer", "Fullstack Developer", "Web Developer"],
            "frontend developer": ["Frontend Engineer", "Front End Developer", "UI Engineer", "React Developer"],
            "backend developer": ["Backend Engineer", "Back End Developer", "Software Engineer", "Python Developer"],
            "devops engineer": ["Site Reliability Engineer", "SRE", "Cloud Engineer", "Platform Engineer"],
            # Product & Project
            "product manager": ["Associate Product Manager", "Technical Product Manager", "Product Owner", "Senior Product Manager"],
            "project manager": ["Program Manager", "Scrum Master", "Delivery Manager"],
            # Data & AI
            "data scientist": ["Machine Learning Engineer", "Data Analyst", "AI Engineer", "Data Specialist"],
            "data analyst": ["Business Analyst", "Data Scientist", "BI Analyst"],
            "machine learning engineer": ["AI Engineer", "ML Engineer", "Data Scientist", "Deep Learning Engineer"],
            # Marketing & Sales
            "marketing manager": ["Digital Marketing Manager", "Growth Marketer", "Marketing Specialist"],
            "growth marketer": ["Growth Hacker", "Performance Marketer", "Digital Marketer"],
            # Quality & Testing
            "qa engineer": ["Quality Assurance Engineer", "SDET", "Software Tester", "Test Automation Engineer"],
        }

        # Check direct lookup or partial match in taxonomy
        found = False
        for k, syn_list in SYNONYM_MAP.items():
            if k in r_lower or r_lower in k:
                for s in syn_list:
                    if s.lower() != r_lower and s not in synonyms:
                        synonyms.append(s)
                found = True
                break

        # If not in taxonomy, generate dynamic variations (stripping/adding Senior/Lead/Engineer/Developer)
        if not found:
            stripped = re.sub(r'(?i)\b(senior|lead|junior|staff|principal|associate|intern)\b', '', r_clean).strip()
            if stripped and stripped.lower() != r_lower:
                synonyms.append(stripped)
            if "developer" in r_lower:
                synonyms.append(r_clean.replace("developer", "engineer").replace("Developer", "Engineer"))
            elif "engineer" in r_lower:
                synonyms.append(r_clean.replace("engineer", "developer").replace("Engineer", "Developer"))

        return synonyms[:5]

    @classmethod
    def build_posts_search_cascade(cls, query_text: str, location: str = "",
                                   target_roles: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Builds an intelligent sequence of search queries to break past LinkedIn feed limits.
        When a feed ends or yields duplicates, the scraper auto-pivots to the next query
        in the cascade without closing the browser.
        """
        raw_query = query_text.strip()
        # Direct URL supplied by user -> single-query cascade
        if raw_query.startswith("http://") or raw_query.startswith("https://"):
            return [{
                "label": "Direct URL Target",
                "url": raw_query,
                "keywords_for_filter": cls.extract_core_keywords(raw_query)
            }]

        clean_roles = cls.clean_role_query(raw_query)
        if target_roles:
            for tr in target_roles:
                tr_clean = tr.strip().strip('"\'')
                if tr_clean and tr_clean.lower() not in [c.lower() for c in clean_roles]:
                    clean_roles.append(tr_clean)

        # Expand roles with industry synonyms
        all_roles: List[str] = []
        for r in clean_roles:
            for s in cls.expand_role_synonyms(r):
                if s.lower() not in [x.lower() for x in all_roles]:
                    all_roles.append(s)

        cascade: List[Dict[str, Any]] = []
        primary_role = clean_roles[0] if clean_roles else "Product Designer"

        # 1. Primary role query (relevance)
        q1 = f'"{primary_role}" (hiring OR "we are hiring" OR "we\'re hiring")'
        enc1 = urllib.parse.quote(q1)
        cascade.append({
            "label": f"Primary: {primary_role}",
            "url": f"https://www.linkedin.com/search/results/content/?keywords={enc1}&sortBy=%22relevance%22",
            "keywords_for_filter": cls.extract_core_keywords(primary_role)
        })

        # 2. Phrasing variation ("hiring <primary_role>")
        q2 = f'"hiring" "{primary_role}"'
        enc2 = urllib.parse.quote(q2)
        cascade.append({
            "label": f"Direct Hiring Phrase: {primary_role}",
            "url": f"https://www.linkedin.com/search/results/content/?keywords={enc2}&sortBy=%22relevance%22",
            "keywords_for_filter": cls.extract_core_keywords(primary_role)
        })

        # 3. Secondary roles / synonyms
        for r in all_roles[1:4]:
            q_syn = f'"{r}" (hiring OR "we are hiring" OR "we\'re hiring")'
            enc_syn = urllib.parse.quote(q_syn)
            cascade.append({
                "label": f"Role Pivot: {r}",
                "url": f"https://www.linkedin.com/search/results/content/?keywords={enc_syn}&sortBy=%22relevance%22",
                "keywords_for_filter": cls.extract_core_keywords(r)
            })

        # 4. Date posted shift (Past 24h / Recent posts) for primary & secondary
        cascade.append({
            "label": f"Recent Date Shift: {primary_role}",
            "url": f"https://www.linkedin.com/search/results/content/?keywords={enc1}&sortBy=%22date_posted%22",
            "keywords_for_filter": cls.extract_core_keywords(primary_role)
        })

        if len(all_roles) > 1:
            r_alt = all_roles[1]
            q_alt = f'"{r_alt}" (hiring OR "we are hiring" OR "we\'re hiring")'
            enc_alt = urllib.parse.quote(q_alt)
            cascade.append({
                "label": f"Recent Date Shift: {r_alt}",
                "url": f"https://www.linkedin.com/search/results/content/?keywords={enc_alt}&sortBy=%22date_posted%22",
                "keywords_for_filter": cls.extract_core_keywords(r_alt)
            })

        return cascade

    @classmethod
    def build_posts_search_query(cls, query_text: str, location: str = "") -> Tuple[str, List[str]]:
        """
        Primary entrypoint: Builds a high-recall, native LinkedIn search query.
        Returns: (compiled_query, core_keywords_for_parser)
        """
        raw_query = query_text.strip()
        core_keywords = cls.extract_core_keywords(raw_query)

        # If user supplied a raw direct URL, return it directly
        if raw_query.startswith("http://") or raw_query.startswith("https://"):
            return raw_query, core_keywords

        compiled = cls.build_deterministic_query(raw_query, location=location)
        return compiled, core_keywords

