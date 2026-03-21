"""3-stage retrieval pipeline: embed -> TPUF filter -> post-filter -> rerank."""

import re
from embed import embed_query
from tpuf_client import query_vector, get_namespace
from filters import apply_hard_filter
from rerank import rerank_candidates


def build_rich_query(config: dict) -> str:
    """Build a rich query string from description + criteria for better embedding."""
    parts = [config["description"]]
    parts.append("Required qualifications: " + "; ".join(config["hard_criteria"]))
    parts.append("Preferred qualifications: " + "; ".join(config["soft_criteria"]))
    return "\n".join(parts)


# TPUF-level attribute filters per config
TPUF_FILTERS = {
    "anthropology.yml": ["And", [
        ["deg_degrees", "ContainsAny", ["Doctorate"]],
        ["deg_start_years", "ContainsAny", ["2023", "2024", "2025", "2026"]],
        ["deg_fos", "ContainsAny", [
            "Anthropology", "Sociology", "Social Anthropology", "Cultural Anthropology",
            "Economics", "Sociocultural Anthropology", "Social Sciences", "Development Studies",
        ]],
    ]],
    "doctors_md.yml": ["And", [
        ["deg_degrees", "ContainsAny", ["MD", "Doctor of Medicine"]],
        ["country", "Eq", "United States"],
    ]],
    "mathematics_phd.yml": ["And", [
        ["deg_degrees", "ContainsAny", ["Doctorate"]],
        ["deg_fos", "ContainsAny", [
            "Mathematics", "Statistics", "Applied Mathematics", "Mathematical Sciences",
            "Probability", "Biostatistics", "Pure Mathematics", "Computational Mathematics",
        ]],
    ]],
    "biology_expert.yml": ["And", [
        ["deg_degrees", "ContainsAny", ["Doctorate"]],
        ["deg_fos", "ContainsAny", [
            "Biology", "Molecular Biology", "Genetics", "Cell Biology", "Biochemistry",
            "Biological Sciences", "Life Sciences", "Biomedical Sciences", "Microbiology",
            "Neuroscience", "Ecology", "Evolutionary Biology",
        ]],
    ]],
    "quantitative_finance.yml": ["And", [
        ["deg_degrees", "ContainsAny", ["MBA"]],
    ]],
}

# Known US/UK/CA school name fragments for undergrad location checks
_US_SCHOOLS = [
    'mit', 'harvard', 'stanford', 'yale', 'princeton', 'columbia', 'cornell', 'berkeley',
    'ucla', 'nyu', 'duke', 'michigan', 'penn', 'chicago', 'caltech', 'georgia tech',
    'illinois', 'wisconsin', 'purdue', 'ohio', 'texas', 'florida', 'virginia',
    'maryland', 'rutgers', 'indiana', 'iowa', 'minnesota', 'arizona', 'colorado',
    'carolina', 'washington', 'boston', 'northwestern', 'carnegie', 'brown', 'rice',
    'emory', 'vanderbilt', 'dartmouth', 'williams', 'amherst', 'swarthmore',
    'tufts', 'notre dame', 'georgetown', 'wake forest', 'tulane', 'rochester',
    'brandeis', 'case western', 'johns hopkins', 'new college', 'new york university',
    'stony brook', 'binghamton', 'suny', 'cuny', 'drexel', 'lehigh', 'villanova',
    'state university', 'institute of technology',
]
_UK_SCHOOLS = [
    'oxford', 'cambridge', 'imperial', 'ucl', 'london', 'edinburgh',
    'manchester', 'bristol', 'warwick', 'glasgow', 'sheffield', 'leeds',
    'nottingham', 'southampton', 'birmingham', 'york', 'durham', 'exeter',
    "king's college", 'st andrews', 'bath', 'surrey', 'sussex', 'lancaster',
]
_CA_SCHOOLS = [
    'toronto', 'mcgill', 'british columbia', 'ubc', 'waterloo',
    'alberta', 'montreal', 'ottawa', "queen's", 'western ontario',
    'simon fraser', 'dalhousie', 'manitoba', 'calgary', 'mcmaster', 'carleton',
]
_TARGET_SCHOOLS = _US_SCHOOLS + _UK_SCHOOLS + _CA_SCHOOLS

# Top US medical schools
_TOP_MED_SCHOOLS = [
    'harvard', 'johns hopkins', 'stanford', 'ucsf', 'columbia', 'penn', 'duke',
    'yale', 'nyu', 'michigan', 'ucla', 'mayo', 'cornell', 'northwestern',
    'washington', 'emory', 'vanderbilt', 'baylor', 'mount sinai', 'pittsburgh',
    'chicago', 'virginia', 'georgetown', 'tufts', 'boston', 'rochester',
    'case western', 'albert einstein', 'icahn', 'weill', 'temple',
    'ohio state', 'wisconsin', 'minnesota', 'iowa', 'colorado', 'usc',
    'south florida', 'miami', 'dartmouth', 'brown', 'einstein',
]


def _has_undergrad_in_target(degrees_list):
    """Check if any bachelor's degree is from a US/UK/CA school."""
    for deg in degrees_list:
        s = str(deg).lower()
        if "bachelor" in s:
            school_match = re.search(r'school_(.*?)::', s)
            if school_match:
                school = school_match.group(1).lower()
                if any(ind in school for ind in _TARGET_SCHOOLS):
                    return True
    return False


def _has_top_med_school(degrees_list):
    """Check if any MD degree is from a top US medical school."""
    for deg in degrees_list:
        s = str(deg).lower()
        if "md" in s or "medicine" in s or "doctor" in s:
            school_match = re.search(r'school_(.*?)::', s)
            if school_match:
                school = school_match.group(1).lower()
                if any(ind in school for ind in _TOP_MED_SCHOOLS):
                    return True
    return False


def _has_quant_title(exp_list):
    """Check if any experience title matches quantitative finance roles."""
    quant_patterns = [
        r'quant', r'risk.*model', r'algorithm.*trad', r'financial.*engineer',
        r'portfolio', r'deriv', r'trader', r'analyst.*quant', r'data.*scien',
        r'investment.*bank', r'hedge.*fund', r'asset.*manag', r'private.*equity',
    ]
    for exp in exp_list:
        s = str(exp).lower()
        for pat in quant_patterns:
            if re.search(pat, s):
                return True
    return False


# Post-retrieval filters that check structured degree/experience strings
POST_FILTERS = {
    "mathematics_phd.yml": lambda candidates: [
        c for c in candidates if _has_undergrad_in_target(c.get("degrees") or [])
    ],
    "biology_expert.yml": lambda candidates: [
        c for c in candidates if _has_undergrad_in_target(c.get("degrees") or [])
    ],
    "doctors_md.yml": lambda candidates: [
        c for c in candidates if _has_top_med_school(c.get("degrees") or [])
    ],
    "quantitative_finance.yml": lambda candidates: [
        c for c in candidates if _has_quant_title(c.get("experience") or [])
    ],
}


def run_pipeline(
    query_config: dict,
    top_k_retrieve: int = 200,
    top_k_final: int = 10,
) -> list[dict]:
    """Run the full pipeline for a single query config."""
    title = query_config["title"]
    description = query_config["description"]
    config_path = query_config["config_path"]
    hard_criteria = query_config["hard_criteria"]
    soft_criteria = query_config["soft_criteria"]

    # Stage 1: Embed rich query and retrieve from TPUF
    rich_query = build_rich_query(query_config)
    print(f"[{title}] Stage 1: Embedding query and retrieving top {top_k_retrieve}...")
    query_vector_emb = embed_query(rich_query)

    tpuf_filter = TPUF_FILTERS.get(config_path)
    if tpuf_filter:
        print(f"  Using TPUF attribute filter")
    candidates = query_vector(query_vector_emb, top_k=top_k_retrieve, filters=tpuf_filter)
    print(f"  Retrieved {len(candidates)} candidates")

    # Stage 2: Post-retrieval structured filtering
    print(f"[{title}] Stage 2: Applying filters...")
    post_fn = POST_FILTERS.get(config_path)
    if post_fn:
        filtered = post_fn(candidates)
        print(f"  {len(filtered)} after post-filter")
        if len(filtered) < 15:
            print(f"  Warning: too few, falling back to basic filter")
            filtered = apply_hard_filter(candidates, config_path)
    else:
        filtered = apply_hard_filter(candidates, config_path)
    print(f"  {len(filtered)} candidates for reranking")

    # Stage 3: LLM re-ranking
    print(f"[{title}] Stage 3: Re-ranking...")
    reranked = rerank_candidates(
        filtered,
        description,
        hard_criteria,
        soft_criteria,
        top_k=top_k_final,
    )
    print(f"  Top {len(reranked)} candidates selected")

    return reranked
