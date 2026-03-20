"""Hard criteria filtering on structured candidate fields.

Intentionally relaxed filters to keep a broad candidate pool.
The LLM reranker handles nuanced criteria like "top school" or recency.
These filters just remove obvious mismatches to reduce LLM calls.
"""

from __future__ import annotations
import re


def _has_degree(candidate, degree_types: list[str]) -> bool:
    """Check if candidate has any of the specified degree types (loose match)."""
    degrees = candidate.get("deg_degrees") or []
    if isinstance(degrees, str):
        degrees = [degrees]
    for d in degrees:
        d_lower = d.lower()
        for dt in degree_types:
            if dt.lower() in d_lower:
                return True
    return False


def _degree_field_matches(candidate, patterns: list[str]) -> bool:
    """Check if any field of study or education string matches."""
    fos = candidate.get("deg_fos") or []
    if isinstance(fos, str):
        fos = [fos]
    degrees_raw = candidate.get("degrees") or []
    if isinstance(degrees_raw, str):
        degrees_raw = [degrees_raw]
    all_text = fos + degrees_raw
    for item in all_text:
        for pat in patterns:
            if re.search(pat, str(item), re.IGNORECASE):
                return True
    return False


def _exp_title_matches(candidate, patterns: list[str]) -> bool:
    """Check if any experience title or experience string matches."""
    titles = candidate.get("exp_titles") or []
    if isinstance(titles, str):
        titles = [titles]
    exps = candidate.get("experience") or []
    if isinstance(exps, str):
        exps = [exps]
    for item in titles + exps:
        for pat in patterns:
            if re.search(pat, str(item), re.IGNORECASE):
                return True
    return False


# ---- Per-config filters (relaxed) ----

def filter_tax_lawyer(candidates):
    return [c for c in candidates if _has_degree(c, ["jd", "juris", "law"])]


def filter_junior_corporate_lawyer(candidates):
    return [c for c in candidates
            if _has_degree(c, ["jd", "juris", "law", "bachelor"])
            and _exp_title_matches(c, [r"lawyer|attorney|counsel|legal|corporate"])]


def filter_radiology(candidates):
    return [c for c in candidates
            if _has_degree(c, ["md", "doctor", "mbbs"])
            or _degree_field_matches(c, [r"medic", r"radiol"])]


def filter_doctors_md(candidates):
    return [c for c in candidates
            if _has_degree(c, ["md", "doctor", "mbbs"])
            or _degree_field_matches(c, [r"medic", r"physician"])]


def filter_biology_expert(candidates):
    return [c for c in candidates
            if _has_degree(c, ["doctor", "phd"])
            and _degree_field_matches(c, [r"bio", r"life science", r"genetics", r"molecular", r"cell"])]


def filter_anthropology(candidates):
    return [c for c in candidates
            if _has_degree(c, ["doctor", "phd"])
            and _degree_field_matches(c, [r"anthrop", r"sociol", r"econom", r"social", r"cultur"])]


def filter_mathematics_phd(candidates):
    return [c for c in candidates
            if _has_degree(c, ["doctor", "phd"])
            and _degree_field_matches(c, [r"math", r"statist", r"applied math", r"comput"])]


def filter_quantitative_finance(candidates):
    return [c for c in candidates
            if _has_degree(c, ["mba", "master"])]


def filter_bankers(candidates):
    return [c for c in candidates
            if _has_degree(c, ["mba", "master"])]


def filter_mechanical_engineers(candidates):
    return [c for c in candidates
            if _degree_field_matches(c, [r"mechanic", r"engineer"])]


FILTER_MAP = {
    "tax_lawyer.yml": filter_tax_lawyer,
    "junior_corporate_lawyer.yml": filter_junior_corporate_lawyer,
    "radiology.yml": filter_radiology,
    "doctors_md.yml": filter_doctors_md,
    "biology_expert.yml": filter_biology_expert,
    "anthropology.yml": filter_anthropology,
    "mathematics_phd.yml": filter_mathematics_phd,
    "quantitative_finance.yml": filter_quantitative_finance,
    "bankers.yml": filter_bankers,
    "mechanical_engineers.yml": filter_mechanical_engineers,
}


def apply_hard_filter(candidates, config_path):
    """Apply relaxed hard criteria filter. Returns filtered list."""
    fn = FILTER_MAP.get(config_path)
    if fn is None:
        return candidates
    filtered = fn(candidates)
    if len(filtered) < 15:
        print(f"  Warning: only {len(filtered)} after filter, using full candidate set")
        return candidates
    return filtered
