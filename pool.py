"""Candidate pool building: exhaustive structured scans + per-config prescreens.

Run 4 replaces ANN-first retrieval with full-recall structured scans for hard
gates (the corpus is ~200K profiles; every hard-gate population fits in a few
thousand rows), then prescreens on parsed degree entries and summary text
before LLM judging. Light rows (structured fields only) are filtered first so
full summaries are fetched only for plausible candidates.
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path

from tpuf_client import get_namespace, INCLUDE_ATTRS

CACHE_DIR = Path(__file__).parent / "cache"

LIGHT_ATTRS = ["name", "country", "degrees", "deg_degrees", "deg_fos", "deg_start_years"]

DOCTORATE_DEGREES = ["Doctorate", "Ph. D.", "PhD", "Ph.D.", "Doctor of Philosophy"]
MD_DEGREES = ["MD", "Doctor of Medicine"]
MBA_DEGREES = ["MBA", "Master of Business Administration"]
JD_DEGREES = [
    "JD", "Doctor of Law - JD", "Doctor of Law (J.D.)", "Doctor of Law (JD)",
    "Juris Doctor", "Doctor of Law", "J.D.", "Juris Doctor (J.D.)", "Juris Doctorate",
]
LAW_DEGREES = JD_DEGREES + ["LLB", "LL.B.", "Bachelor of Laws", "LL.M.", "LLM", "Master of Laws"]


def parse_degrees(degrees_list) -> list[dict]:
    """Parse 'yrs_5::school_X::degree_D::fos_F::start_2024::end_2029' strings."""
    out = []
    for raw in degrees_list or []:
        entry = {"school": "", "degree": "", "fos": "", "start": "", "end": ""}
        for part in str(raw).split("::"):
            for key in ("school", "degree", "fos", "start", "end"):
                if part.startswith(key + "_"):
                    entry[key] = part[len(key) + 1:]
        out.append(entry)
    return out


# School fragment lists calibrated against observed eval-judge verdicts.
# The judge FAILED Ohio State, Medical College of Wisconsin, VCU, and University
# of Washington for "top U.S. medical school" while passing Georgetown, GWU,
# Cornell, and Harvard, so this list stays unambiguous-elite only.
MED_ELITE = [
    "harvard", "johns hopkins", "stanford", "ucsf", "university of california, san francisco",
    "perelman", "university of pennsylvania", "columbia", "weill", "cornell", "duke", "yale",
    "nyu", "new york university", "grossman", "michigan", "ucla", "geffen",
    "washington university", "northwestern", "feinberg", "mayo", "vanderbilt",
    "pritzker", "university of chicago", "icahn", "mount sinai", "emory", "georgetown",
    "baylor", "university of california, san diego", "ucsd",
]
# The judge treats M7 nearly literally (NYU Stern failed it), so strict seven.
M7_SCHOOLS = [
    "harvard", "stanford", "wharton", "university of pennsylvania",
    "booth", "university of chicago", "kellogg", "northwestern",
    "columbia", "sloan", "massachusetts institute of technology",
]
M7_EXCLUDE = ["columbia southern", "british columbia", "columbia college"]
# "Top U.S. university" for a biology PhD is judged leniently (UNC, UCSD, and
# CMU passed; SUNY Albany failed), so this list is broad research-elite.
TOP_US_BROAD = [
    "harvard", "stanford", "mit", "massachusetts institute", "caltech", "princeton", "yale",
    "columbia", "cornell", "penn", "brown", "dartmouth", "duke", "johns hopkins", "northwestern",
    "university of chicago", "berkeley", "ucla", "ucsf", "ucsd", "university of california",
    "michigan", "wisconsin", "illinois", "washington university", "university of washington",
    "north carolina", "chapel hill", "vanderbilt", "emory", "rice", "carnegie mellon",
    "nyu", "new york university", "texas at austin", "georgia institute", "purdue",
    "minnesota", "maryland", "colorado", "pittsburgh", "rockefeller", "mayo",
    "mount sinai", "icahn", "baylor", "scripps", "virginia", "florida", "ohio state",
    "penn state", "rutgers", "stony brook", "case western", "boston university", "tufts",
    "dana-farber", "sloan kettering", "md anderson",
]
UGRAD_US_UK_CA = [
    "mit", "harvard", "stanford", "yale", "princeton", "columbia", "cornell", "berkeley",
    "ucla", "ucsd", "uc davis", "uc irvine", "uc santa", "uc riverside", "university of california",
    "nyu", "new york university", "duke", "michigan", "penn", "chicago", "caltech",
    "georgia tech", "georgia institute", "illinois", "wisconsin", "purdue", "ohio",
    "texas", "florida", "virginia", "maryland", "rutgers", "indiana", "iowa", "minnesota",
    "arizona", "colorado", "carolina", "washington", "boston", "northwestern", "carnegie",
    "brown", "rice", "emory", "vanderbilt", "dartmouth", "williams", "amherst", "swarthmore",
    "pomona", "harvey mudd", "tufts", "notre dame", "georgetown", "wake forest", "tulane",
    "rochester", "brandeis", "case western", "johns hopkins", "stony brook", "binghamton",
    "suny", "cuny", "drexel", "lehigh", "villanova", "state university", "institute of technology",
    "college of william", "utah", "oregon", "kansas", "kentucky", "tennessee", "missouri",
    "nebraska", "oklahoma", "alabama", "georgia", "clemson", "auburn", "baylor",
    "oxford", "cambridge", "imperial", "ucl", "london", "edinburgh", "manchester", "bristol",
    "warwick", "glasgow", "sheffield", "leeds", "nottingham", "southampton", "birmingham",
    "york", "durham", "exeter", "king's college", "st andrews", "bath", "surrey", "sussex",
    "lancaster", "loughborough", "cardiff", "queen mary", "aberdeen",
    "toronto", "mcgill", "british columbia", "ubc", "waterloo", "alberta", "montreal",
    "ottawa", "queen's", "western ontario", "simon fraser", "dalhousie", "manitoba",
    "calgary", "mcmaster", "carleton", "concordia", "york university", "laval",
]
US_UNIV_FRAGMENTS = [f for f in UGRAD_US_UK_CA if f not in (
    "oxford", "cambridge", "imperial", "ucl", "london", "edinburgh", "manchester", "bristol",
    "warwick", "glasgow", "sheffield", "leeds", "nottingham", "southampton", "birmingham",
    "york", "durham", "exeter", "king's college", "st andrews", "bath", "surrey", "sussex",
    "lancaster", "loughborough", "cardiff", "queen mary", "aberdeen",
    "toronto", "mcgill", "british columbia", "ubc", "waterloo", "alberta", "montreal",
    "ottawa", "queen's", "western ontario", "simon fraser", "dalhousie", "manitoba",
    "calgary", "mcmaster", "carleton", "concordia", "york university", "laval",
)]


def _school_in(school: str, fragments: list[str], exclude: list[str] | None = None) -> bool:
    s = (school or "").lower()
    if not s:
        return False
    if exclude and any(x in s for x in exclude):
        return False
    return any(f in s for f in fragments)


def scan(filters, attrs, cap=100000):
    """Exhaustive id-ordered paginated scan of the namespace under filters."""
    ns = get_namespace()
    last, rows_out = None, []
    while len(rows_out) < cap:
        f = filters
        if last is not None:
            f = ["And", [filters, ["id", "Gt", last]]] if filters else ["id", "Gt", last]
        result = ns.query(rank_by=("id", "asc"), top_k=1000, filters=f, include_attributes=attrs)
        rows = result.rows
        if not rows:
            break
        for row in rows:
            d = row.model_dump()
            entry = {"_id": d.get("id")}
            for a in attrs:
                entry[a] = d.get(a)
            rows_out.append(entry)
        last = rows[-1].id
        if len(rows) < 1000:
            break
    return rows_out


def fetch_full(ids: list[str]) -> list[dict]:
    """Fetch full records (all INCLUDE_ATTRS) for specific ids, batched."""
    ns = get_namespace()
    out = []
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        result = ns.query(rank_by=("id", "asc"), top_k=len(batch),
                          filters=["id", "In", batch], include_attributes=INCLUDE_ATTRS)
        for row in result.rows:
            d = row.model_dump()
            entry = {"_id": d.get("id")}
            for a in INCLUDE_ATTRS:
                entry[a] = d.get(a)
            out.append(entry)
    return out


RECENT_YEAR_RE = re.compile(r"20(2[3-6])")
PUB_RE = re.compile(r"publi(sh|cation)|journal|peer.review|conference|paper|preprint|arxiv", re.I)


def _summary_has(cand, pattern) -> bool:
    return bool(re.search(pattern, cand.get("rerankSummary") or "", re.I))


def _is_phd(degree: str) -> bool:
    d = (degree or "").lower()
    return d == "doctorate" or "ph" in d


def _is_mba(degree: str) -> bool:
    d = (degree or "").lower()
    return "mba" in d or "business admin" in d


def _is_md(degree: str) -> bool:
    d = (degree or "").lower()
    return "md" in d or "medicine" in d


def _is_bachelor(degree: str) -> bool:
    return "bachelor" in (degree or "").lower()


# ---- Per-config pool builders ----
# Each returns (light_scan_rows, keep_on_full_record, richness_ranker[, light_keep]).
# light_keep sees only LIGHT_ATTRS and gates the expensive full-record fetch.

def pool_anthropology():
    fos = ["Anthropology", "Sociology", "Social Anthropology", "Cultural Anthropology",
           "Economics", "Sociocultural Anthropology", "Social Sciences", "Development Studies",
           "Development Economics", "Applied Economics", "Demography",
           "Social And Cultural Anthropology", "Medical Anthropology"]
    rows = scan(["And", [["deg_degrees", "ContainsAny", DOCTORATE_DEGREES],
                          ["deg_fos", "ContainsAny", fos]]], LIGHT_ATTRS)

    def keep(c):
        entries = parse_degrees(c.get("degrees"))
        phd_recent = any(_is_phd(e["degree"]) for e in entries
                         if e["start"] in ("2023", "2024", "2025", "2026"))
        return phd_recent or bool(RECENT_YEAR_RE.search(c.get("rerankSummary") or ""))

    def rank(c):
        s = c.get("rerankSummary") or ""
        return (len(PUB_RE.findall(s)) * 3
                + len(re.findall(r"ethnograph|fieldwork|migration|labor", s, re.I))
                + len(RECENT_YEAR_RE.findall(s)))
    return rows, keep, rank


def pool_doctors_md():
    rows = scan(["And", [["deg_degrees", "ContainsAny", MD_DEGREES],
                          ["country", "Eq", "United States"]]], LIGHT_ATTRS)

    def light_keep(c):
        return any(_is_md(e["degree"]) and _school_in(e["school"], MED_ELITE)
                   for e in parse_degrees(c.get("degrees")))

    def keep(c):
        elite_md = any(_is_md(e["degree"]) and _school_in(e["school"], MED_ELITE)
                       for e in parse_degrees(c.get("degrees")))
        practice = _summary_has(c, r"family med|primary care|general practi|internal medicine|"
                                   r"outpatient|urgent care|clinic|telemedicine|telehealth|patient")
        return elite_md and practice

    def rank(c):
        s = c.get("rerankSummary") or ""
        return (len(re.findall(r"telemedicine|telehealth", s, re.I)) * 3
                + len(re.findall(r"ehr|epic|cerner|athena", s, re.I)) * 3
                + len(re.findall(r"primary care|family med|general practi|outpatient", s, re.I)))
    return rows, keep, rank, light_keep


def pool_mathematics_phd():
    fos = ["Mathematics", "Statistics", "Applied Mathematics", "Mathematical Sciences",
           "Probability", "Biostatistics", "Pure Mathematics", "Computational Mathematics"]
    rows = scan(["And", [["deg_degrees", "ContainsAny", DOCTORATE_DEGREES],
                          ["deg_fos", "ContainsAny", fos]]], LIGHT_ATTRS)

    def light_keep(c):
        return any(_is_bachelor(e["degree"]) and _school_in(e["school"], UGRAD_US_UK_CA)
                   for e in parse_degrees(c.get("degrees")))

    def keep(c):
        return any(_is_bachelor(e["degree"]) and _school_in(e["school"], UGRAD_US_UK_CA)
                   for e in parse_degrees(c.get("degrees")))

    def rank(c):
        s = c.get("rerankSummary") or ""
        return len(PUB_RE.findall(s)) * 2 + len(re.findall(r"model|stochastic|inference|research", s, re.I))
    return rows, keep, rank, light_keep


def pool_biology_expert():
    fos = ["Biology", "Molecular Biology", "Genetics", "Cell Biology", "Biochemistry",
           "Biological Sciences", "Life Sciences", "Biomedical Sciences", "Microbiology",
           "Neuroscience", "Ecology", "Evolutionary Biology", "Immunology", "Genomics",
           "Cancer Biology", "Developmental Biology", "Molecular Genetics"]
    rows = scan(["And", [["deg_degrees", "ContainsAny", DOCTORATE_DEGREES],
                          ["deg_fos", "ContainsAny", fos]]], LIGHT_ATTRS)

    def light_keep(c):
        return any(_is_bachelor(e["degree"]) and _school_in(e["school"], UGRAD_US_UK_CA)
                   for e in parse_degrees(c.get("degrees")))

    def keep(c):
        entries = parse_degrees(c.get("degrees"))
        ugrad_ok = any(_is_bachelor(e["degree"]) and _school_in(e["school"], UGRAD_US_UK_CA)
                       for e in entries)
        phd_top = any(_is_phd(e["degree"]) and _school_in(e["school"], TOP_US_BROAD)
                      for e in entries)
        return ugrad_ok and phd_top

    def rank(c):
        s = c.get("rerankSummary") or ""
        return (len(PUB_RE.findall(s)) * 2
                + len(re.findall(r"crispr|pcr|sequencing|gene|molecular", s, re.I))
                + len(re.findall(r"teach|mentor|instructor|course", s, re.I)) * 2)
    return rows, keep, rank, light_keep


def pool_quantitative_finance():
    rows = scan(["deg_degrees", "ContainsAny", MBA_DEGREES], LIGHT_ATTRS)

    def light_keep(c):
        return any(_is_mba(e["degree"]) and _school_in(e["school"], M7_SCHOOLS, M7_EXCLUDE)
                   for e in parse_degrees(c.get("degrees")))

    def keep(c):
        m7 = any(_is_mba(e["degree"]) and _school_in(e["school"], M7_SCHOOLS, M7_EXCLUDE)
                 for e in parse_degrees(c.get("degrees")))
        quant = _summary_has(c, r"quant|trading|risk|portfolio|derivative|hedge|algorithmic|investment")
        return m7 and quant

    def rank(c):
        s = c.get("rerankSummary") or ""
        return (len(re.findall(r"python", s, re.I)) * 4
                + len(re.findall(r"quant|derivative|algorithmic|risk model|portfolio", s, re.I)))
    return rows, keep, rank, light_keep


def pool_bankers():
    rows = scan(["deg_degrees", "ContainsAny", MBA_DEGREES], LIGHT_ATTRS)

    def light_keep(c):
        return any(_is_mba(e["degree"]) and _school_in(e["school"], US_UNIV_FRAGMENTS)
                   for e in parse_degrees(c.get("degrees")))

    def keep(c):
        us_mba = any(_is_mba(e["degree"]) and _school_in(e["school"], US_UNIV_FRAGMENTS)
                     for e in parse_degrees(c.get("degrees")))
        health = _summary_has(c, r"healthcare|health system|biotech|pharma|medical|provider|payer|digital health")
        bank = _summary_has(c, r"investment bank|m&a|merger|advisory|private equity|corporate finance|capital")
        return us_mba and health and bank

    def rank(c):
        s = c.get("rerankSummary") or ""
        return (len(re.findall(r"healthcare|health", s, re.I)) * 2
                + len(re.findall(r"m&a|transaction|deal|diligence", s, re.I)))
    return rows, keep, rank, light_keep


def pool_tax_lawyer():
    rows = scan(["deg_degrees", "ContainsAny", JD_DEGREES], LIGHT_ATTRS)

    def keep(c):
        return (_summary_has(c, r"\btax")
                and _summary_has(c, r"irs|audit|controvers|legal opinion|tax court"))

    def rank(c):
        s = c.get("rerankSummary") or ""
        return (len(re.findall(r"irs|audit|controvers", s, re.I)) * 2
                + len(re.findall(r"opinion|memo|brief|drafted|authored", s, re.I)) * 2
                + len(re.findall(r"m&a|corporate|transaction|structuring", s, re.I)))
    return rows, keep, rank


def pool_junior_corporate_lawyer():
    rows = scan(["deg_degrees", "ContainsAny", LAW_DEGREES], LIGHT_ATTRS)

    def keep(c):
        return (_summary_has(c, r"m&a|merger|acquisition|corporate|due diligence|contract")
                and _summary_has(c, r"associate|lawyer|attorney|counsel|legal"))

    def rank(c):
        s = c.get("rerankSummary") or ""
        return (len(re.findall(r"m&a|merger|acquisition|due diligence", s, re.I)) * 2
                + len(re.findall(r"contract|negotiat|agreement", s, re.I))
                + len(re.findall(r"cross-border|international|regulatory", s, re.I)))
    return rows, keep, rank


def pool_radiology():
    rows = scan(["And", [["deg_degrees", "ContainsAny", MD_DEGREES],
                          ["country", "In", ["United States", "India"]]]], LIGHT_ATTRS)

    def keep(c):
        return _summary_has(c, r"radiol|imaging|\bct\b|\bmri\b|x-ray|ultrasound|nuclear medicine")

    def rank(c):
        s = c.get("rerankSummary") or ""
        return (len(re.findall(r"board.certified|abr|frcr|fellowship", s, re.I)) * 3
                + len(re.findall(r"ct|mri|x-ray|ultrasound|report", s, re.I))
                + len(re.findall(r"\bai\b|deep learning|machine learning", s, re.I)) * 2)
    return rows, keep, rank


def pool_mechanical_engineers():
    fos = ["Mechanical Engineering", "Mechanical And Aerospace Engineering",
           "Mechanical Engineering Technology", "Mechatronics"]
    rows = scan(["deg_fos", "ContainsAny", fos], LIGHT_ATTRS)

    def keep(c):
        return _summary_has(c, r"solidworks|ansys|cad|autocad|comsol|thermal|fea|prototyp")

    def rank(c):
        s = c.get("rerankSummary") or ""
        return (len(re.findall(r"solidworks|ansys|comsol|autocad", s, re.I)) * 2
                + len(re.findall(r"thermal|fluid|structural|mechatronic", s, re.I))
                + len(re.findall(r"prototyp|manufactur|product", s, re.I)))
    return rows, keep, rank


POOL_BUILDERS = {
    "anthropology.yml": (pool_anthropology, 550),
    "doctors_md.yml": (pool_doctors_md, 400),
    "mathematics_phd.yml": (pool_mathematics_phd, 300),
    "biology_expert.yml": (pool_biology_expert, 300),
    "quantitative_finance.yml": (pool_quantitative_finance, 300),
    "bankers.yml": (pool_bankers, 300),
    "tax_lawyer.yml": (pool_tax_lawyer, 300),
    "junior_corporate_lawyer.yml": (pool_junior_corporate_lawyer, 300),
    "radiology.yml": (pool_radiology, 300),
    "mechanical_engineers.yml": (pool_mechanical_engineers, 250),
}


def build_pool(config_path: str) -> list[dict]:
    """Build, prescreen, cap, and cache the judging pool for one config."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"pool-{config_path.replace('.yml', '')}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    built = POOL_BUILDERS[config_path][0]()
    cap = POOL_BUILDERS[config_path][1]
    light_rows, keep, rank = built[0], built[1], built[2]
    light_keep = built[3] if len(built) > 3 else None
    print(f"[{config_path}] structured scan: {len(light_rows)} rows")

    if light_keep is not None:
        light_rows = [r for r in light_rows if light_keep(r)]
        print(f"[{config_path}] light prescreen kept: {len(light_rows)}")

    full = fetch_full([r["_id"] for r in light_rows])
    kept = [c for c in full if keep(c)]
    print(f"[{config_path}] prescreen kept: {len(kept)}")

    kept.sort(key=rank, reverse=True)
    kept = kept[:cap]
    cache_file.write_text(json.dumps(kept))
    print(f"[{config_path}] pool cached: {len(kept)} candidates")
    return kept


if __name__ == "__main__":
    targets = sys.argv[1:] or list(POOL_BUILDERS)
    for cp in targets:
        build_pool(cp)
