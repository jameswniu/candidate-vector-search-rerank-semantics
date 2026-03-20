"""LLM-based re-ranking of candidates on hard + soft criteria."""

from __future__ import annotations
import json
import re
import os
from openai import OpenAI


OAI_KEY = os.environ["OPENAI_API_KEY"]


def rerank_candidates(
    candidates: list[dict],
    query_description: str,
    hard_criteria: list[str],
    soft_criteria: list[str],
    top_k: int = 10,
    batch_size: int = 5,
) -> list[dict]:
    """Re-rank candidates using GPT-4o-mini based on hard + soft criteria fit.

    Candidates that fail hard criteria get score 0.
    Remaining candidates scored 1-10 on soft criteria.
    """
    client = OpenAI(api_key=OAI_KEY)
    hard_text = "\n".join(f"- {c}" for c in hard_criteria)
    soft_text = "\n".join(f"- {c}" for c in soft_criteria)

    scored = []
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        profiles = []
        for j, c in enumerate(batch):
            summary = c.get("rerankSummary") or ""
            # Add structured data the LLM can use
            degrees = c.get("degrees") or c.get("education") or []
            experience = c.get("experience") or []
            country = c.get("country") or ""
            deg_info = "\n".join(f"  {d}" for d in (degrees if isinstance(degrees, list) else [degrees]))
            exp_info = "\n".join(f"  {e}" for e in (experience if isinstance(experience, list) else [experience]))

            profiles.append(
                f"[{j}] Name: {c.get('name', '?')}\n"
                f"Country: {country}\n"
                f"Degrees:\n{deg_info}\n"
                f"Experience:\n{exp_info}\n"
                f"Summary: {summary[:600]}"
            )

        profiles_text = "\n\n---\n\n".join(profiles)
        prompt = (
            f"You are evaluating candidates for this role:\n{query_description}\n\n"
            f"HARD CRITERIA (must-have, candidate MUST meet ALL of these):\n{hard_text}\n\n"
            f"SOFT CRITERIA (nice-to-have, score higher if they match more):\n{soft_text}\n\n"
            f"For each candidate below:\n"
            f"1. Check if they meet ALL hard criteria. If ANY hard criterion is not met, score = 0.\n"
            f"2. If all hard criteria pass, score 1-10 based on soft criteria match.\n\n"
            f"Candidates:\n{profiles_text}\n\n"
            f"Return ONLY a JSON array: [{{\"index\": 0, \"score\": 8, \"hard_pass\": true}}, ...]\n"
            f"Sorted by score descending."
        )

        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=500,
            )
            text = resp.choices[0].message.content.strip()
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                rankings = json.loads(match.group())
                for r in rankings:
                    idx = r.get("index", 0)
                    score = r.get("score", 0)
                    hard_pass = r.get("hard_pass", False)
                    if 0 <= idx < len(batch):
                        candidate = batch[idx].copy()
                        candidate["llm_score"] = score if hard_pass else 0
                        candidate["hard_pass"] = hard_pass
                        scored.append(candidate)
            else:
                for c in batch:
                    c["llm_score"] = 0
                    c["hard_pass"] = False
                    scored.append(c)
        except Exception as e:
            print(f"  Rerank batch error: {e}")
            for c in batch:
                c["llm_score"] = 0
                c["hard_pass"] = False
                scored.append(c)

    # Sort: hard_pass first, then by score
    scored.sort(key=lambda x: (x.get("hard_pass", False), x.get("llm_score", 0)), reverse=True)
    return scored[:top_k]
