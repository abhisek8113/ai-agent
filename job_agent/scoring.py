"""Fast, local suitability scoring — "how much this job suits me".

This is a cheap keyword-overlap heuristic (no API calls), so the dashboard can
score and filter hundreds of jobs instantly. The precise match score still
comes from the tailoring agent; this is the quick pre-filter.
"""

from __future__ import annotations

import re

# Common data-science terms we recognise even if not in the profile skills.
_BONUS_TERMS = {
    "python", "sql", "machine learning", "ml", "data science", "pandas",
    "numpy", "scikit", "power bi", "tableau", "statistics", "nlp",
    "deep learning", "tensorflow", "pytorch", "analytics", "etl",
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]+", (text or "").lower()))


def suitability_score(job_title: str, job_description: str, profile: dict) -> int:
    """Return a 0–100 fit score from profile skills vs the job text.

    Title matches weigh more than description matches. The candidate's own
    skills weigh more than the generic bonus terms.
    """
    skills = [str(s).lower() for s in profile.get("skills", [])]
    role = str(profile.get("role_target", "")).lower()

    title = (job_title or "").lower()
    desc = (job_description or "").lower()
    hay = f"{title} {desc}"

    if not skills and not role:
        return 0

    score = 0.0
    weight_total = 0.0

    # Role alignment in the title is the strongest single signal.
    weight_total += 30
    if role and any(w in title for w in role.split()):
        score += 30
    elif role and any(w in desc for w in role.split()):
        score += 15

    # Each profile skill present adds up to the remaining 55 points.
    if skills:
        weight_total += 55
        hits = sum(1 for s in skills if s and s in hay)
        score += 55 * (hits / len(skills))

    # Generic DS terms add a small 15-point bonus.
    weight_total += 15
    bonus_hits = sum(1 for t in _BONUS_TERMS if t in hay)
    score += 15 * min(1.0, bonus_hits / 6)

    return round(100 * score / weight_total) if weight_total else 0
