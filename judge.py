"""Local judge that tracks the evaluation endpoint's LLM judge.

The eval endpoint scores each submitted candidate as 0 if any hard criterion
fails, else mean(soft scores) * 10, judged by an LLM that sees only the
profile text (rerankSummary), not the structured degree fields. This module
reproduces that rubric so candidates can be verified per-criterion BEFORE
submission. Calibration notes encode observed verdict patterns from real
eval responses (which schools pass "top", what counts as dated evidence).

Runs against any OpenAI-compatible API (OPENAI_API_KEY, optional
OPENAI_BASE_URL, JUDGE_MODEL). Judgments are cached per candidate; an
external harness may also produce the same cache files.
"""

from __future__ import annotations
import asyncio
import json
import os
import re
import sys
from pathlib import Path

JUDGE_PROMPT_VERSION = "v1"

CACHE_DIR = Path(__file__).parent / "cache"
CONFIGS_PATH = Path(__file__).parent / "configs" / "queries.json"

CALIBRATION = {
    "doctors_md.yml": (
        "For 'MD from a top U.S. medical school': PASS only nationally elite schools "
        "(Harvard, Johns Hopkins, Stanford, UCSF, Penn, Columbia, Cornell/Weill, Duke, Yale, "
        "NYU, Michigan, UCLA, Washington University in St. Louis, Northwestern, Mayo, "
        "Vanderbilt, University of Chicago, Mount Sinai, Emory, Georgetown, Baylor, UCSD). "
        "Solid-but-not-elite schools (Ohio State, Medical College of Wisconsin, VCU, "
        "University of Washington, most state schools) FAIL. When ambiguous, FAIL."
    ),
    "quantitative_finance.yml": (
        "'M7 MBA' means strictly Harvard, Stanford, Wharton, Chicago Booth, Northwestern "
        "Kellogg, Columbia, or MIT Sloan. Any other school FAILS, including NYU Stern and "
        "London Business School."
    ),
    "biology_expert.yml": (
        "'Top U.S. university' is interpreted broadly: any strong U.S. research university "
        "passes (UNC, UCSD, Carnegie Mellon pass; regional schools like SUNY Albany fail). "
        "The undergraduate-location criterion requires the undergraduate institution to be "
        "visible in the profile and located in the U.S., U.K., or Canada; if no undergraduate "
        "degree is listed, it FAILS."
    ),
    "anthropology.yml": (
        "'PhD program started within the last 3 years' (current year is 2026): PASS only when "
        "the profile text contains dated evidence: an explicit program start year 2023-2026, a "
        "prior degree completed 2023 or later followed by the PhD, roles dated 2023+ that imply "
        "the program began then (e.g. first TA term Winter 2024), or phrases like "
        "first-year/second-year/incoming PhD student. With no dated signal, FAIL. "
        "'Distinguished program' is judged leniently (any recognized university "
        "anthropology/sociology/economics PhD passes)."
    ),
    "mathematics_phd.yml": (
        "'Completed undergraduate studies in the U.S., U.K., or Canada' requires the "
        "undergraduate institution to be visible in the profile and located there (e.g. Moscow "
        "State University fails). If no undergraduate degree is listed, FAIL. 'Top U.S. "
        "university' for the PhD is judged moderately leniently."
    ),
    "radiology.yml": (
        "'MD degree from a medical school in the U.S. or India' requires an explicit MD degree "
        "visible in the profile education/text; a residency alone without a listed MD FAILS. "
        "Indian MD (Radiodiagnosis) degrees PASS."
    ),
    "junior_corporate_lawyer.yml": (
        "The experience criterion is really about working as a corporate lawyer AT a leading "
        "law firm or in-house at a major global organization in the USA/Europe/Canada; the "
        "judge passes candidates with MORE than 4 years too, but FAILS candidates whose "
        "corporate experience is not at recognizable leading firms/organizations."
    ),
    "tax_lawyer.yml": "",
    "bankers.yml": "",
    "mechanical_engineers.yml": "",
}


def load_configs() -> list[dict]:
    return json.loads(CONFIGS_PATH.read_text())


def get_config(config_path: str) -> dict:
    for c in load_configs():
        if c["config_path"] == config_path:
            return c
    raise KeyError(config_path)


def build_judge_prompt(config: dict, cand: dict) -> str:
    hard = "\n".join(f"{i+1}. {c}" for i, c in enumerate(config["hard_criteria"]))
    soft = "\n".join(f"{i+1}. {c}" for i, c in enumerate(config["soft_criteria"]))
    calibration = CALIBRATION.get(config["config_path"], "")
    calibration_block = f"\nGRADER CALIBRATION:\n{calibration}\n" if calibration else ""
    summary = (cand.get("rerankSummary") or "")[:7000]
    return (
        "You are an expert recruiter evaluating ONE candidate profile against a role "
        "specification. Judge ONLY from the profile text. Do not assume facts not in "
        "evidence, but reasonable inference from dated or strongly indicative signals "
        "is allowed.\n\n"
        f"ROLE:\n{config['description']}\n\n"
        f"HARD CRITERIA (must-have):\n{hard}\n\n"
        f"SOFT CRITERIA (nice-to-have):\n{soft}\n"
        f"{calibration_block}\n"
        f"PROFILE:\n{summary}\n\n"
        "Scoring rules:\n"
        "- Each hard criterion PASSES only with explicit or strongly-inferable evidence in "
        "the profile; if evidence is missing, ambiguous, or unclear, it FAILS.\n"
        "- Each soft criterion is scored 0-10: 9-10 explicit extensive evidence, 7-8 clear "
        "evidence, 5-6 partial or inferred, 3-4 weak, 0-2 none.\n"
        "- For experience-duration hard criteria (2+ years, 3+ years, 2-4 years): count only "
        "full-time professional roles whose dated tenures or explicit statements cover the "
        "required span. Internships, summer roles, part-time student positions, and undated "
        "role lists do NOT satisfy duration. If the span cannot be established from the text, "
        "FAIL.\n"
        "- For role-type hard criteria (experience AS a specific role or IN a specific "
        "function), the actual job titles and employers in the profile must match that "
        "function directly. Adjacent functions do not count (management consulting is not "
        "investment banking; private equity investing is not M&A advisory; an industry "
        "corporate role is not law-firm practice) unless the criterion explicitly includes "
        "them.\n\n"
        "Return ONLY JSON: "
        '{"hard": [{"criterion": <1-based index>, "passes": true/false, '
        '"evidence": "<short quote or reason>"}], '
        '"soft": [{"criterion": <1-based index>, "score": <0-10>}]} '
        "with exactly one entry per criterion."
    )


def parse_judgment(text: str, n_hard: int, n_soft: int) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    hard = data.get("hard") or []
    soft = data.get("soft") or []
    if len(hard) != n_hard or len(soft) != n_soft:
        return None
    try:
        hard_out = [{"criterion": int(h.get("criterion", i + 1)),
                     "passes": bool(h.get("passes", False)),
                     "evidence": str(h.get("evidence", ""))[:300]}
                    for i, h in enumerate(hard)]
        soft_out = [{"criterion": int(s.get("criterion", i + 1)),
                     "score": float(s.get("score", 0))}
                    for i, s in enumerate(soft)]
    except (TypeError, ValueError):
        return None
    all_pass = all(h["passes"] for h in hard_out)
    scores = [s["score"] for s in soft_out]
    predicted = round(sum(scores) / len(scores) * 10, 2) if (all_pass and scores) else 0.0
    return {"hard": hard_out, "soft": soft_out, "predicted": predicted}


def _cand_cache_file(stem: str, cand_id: str) -> Path:
    return CACHE_DIR / f"judgments-{stem}" / f"{cand_id}.json"


def load_cached_judgment(stem: str, cand_id: str) -> dict | None:
    f = _cand_cache_file(stem, cand_id)
    if f.exists():
        data = json.loads(f.read_text())
        if data.get("version") == JUDGE_PROMPT_VERSION:
            return data["judgment"]
    return None


def save_judgment(stem: str, cand_id: str, judgment: dict, model: str):
    f = _cand_cache_file(stem, cand_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"version": JUDGE_PROMPT_VERSION, "model": model,
                             "judgment": judgment}))


async def _judge_one(client, sem, model, config, cand, stem):
    cached = load_cached_judgment(stem, cand["_id"])
    if cached is not None:
        return cand["_id"], cached
    prompt = build_judge_prompt(config, cand)
    n_hard, n_soft = len(config["hard_criteria"]), len(config["soft_criteria"])
    async with sem:
        for attempt in range(3):
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=700,
                )
                judgment = parse_judgment(resp.choices[0].message.content, n_hard, n_soft)
                if judgment is not None:
                    save_judgment(stem, cand["_id"], judgment, model)
                    return cand["_id"], judgment
            except Exception as e:
                if attempt == 2:
                    print(f"  judge error {cand['_id']}: {e}")
                await asyncio.sleep(2 * (attempt + 1))
    return cand["_id"], None


async def judge_pool(config_path: str, model: str):
    from openai import AsyncOpenAI
    stem = config_path.replace(".yml", "")
    pool = json.loads((CACHE_DIR / f"pool-{stem}.json").read_text())
    config = get_config(config_path)
    base_url = os.environ.get("OPENAI_BASE_URL") or None
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=base_url)
    sem = asyncio.Semaphore(24)
    results = await asyncio.gather(*[
        _judge_one(client, sem, model, config, c, stem) for c in pool
    ])
    merged = {cid: j for cid, j in results if j is not None}
    (CACHE_DIR / f"judgments-{stem}.json").write_text(json.dumps(merged))
    passing = sum(1 for j in merged.values() if j["predicted"] > 0)
    print(f"[{config_path}] judged {len(merged)}/{len(pool)}; hard-pass {passing}; "
          f"top predicted: {sorted((j['predicted'] for j in merged.values()), reverse=True)[:10]}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python judge.py <config.yml>")
        sys.exit(1)
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Set it (any OpenAI-compatible provider via "
              "OPENAI_BASE_URL) or produce cache/judgments-<config>.json externally.")
        sys.exit(3)
    model = os.environ.get("JUDGE_MODEL", "gpt-4o-mini")
    asyncio.run(judge_pool(sys.argv[1], model))


if __name__ == "__main__":
    main()
