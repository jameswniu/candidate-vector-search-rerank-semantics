# Candidate Search Pipeline

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)
![Voyage-3](https://img.shields.io/badge/embedding-Voyage--3-orange)
![GPT-4o-mini](https://img.shields.io/badge/reranker-GPT--4o--mini-green)
![Turbopuffer](https://img.shields.io/badge/vector%20DB-Turbopuffer-purple)

Three-stage retrieval pipeline for matching candidates to role specifications: vector retrieval, hard-criteria filtering, and LLM reranking. Given ~200K LinkedIn profiles in a Turbopuffer vector DB (embedded with voyage-3), returns the 10 best-fit candidates for each of 10 role configs. Each config has hard criteria (must-have) and soft criteria (nice-to-have), scored by an evaluation endpoint on hard pass rate and soft relevance (0-10).

## The Problem

You have a vector database of candidate profiles and a role spec with both hard requirements (JD degree, 3+ years experience) and soft preferences (IRS audit exposure, legal writing). Embedding similarity alone conflates these, returning candidates who are semantically close but missing hard requirements entirely.

## What This Does

1. **Vector retrieval**: Embed a rich query (description + hard + soft criteria) with Voyage-3, retrieve top 200 from Turbopuffer via ANN search. For 5 configs, Turbopuffer attribute filters (degree type, start year) narrow results at query time
2. **Hard-criteria filtering**: Python-level regex filters on degree type, field of study, and experience titles. Intentionally relaxed to preserve recall, with a fallback to the full candidate set if fewer than 15 pass
3. **LLM reranking**: GPT-4o-mini scores each candidate on hard + soft criteria. Hard failures get score 0. Remaining candidates scored 1-10 on soft criteria fit

## Architecture

```mermaid
flowchart TD
    Q["Role Spec"] --> EMB["Voyage-3 Embed"]
    EMB --> DB["Turbopuffer ANN · top 200"]
    DB --> AF["Attribute Filter · degree, year, field"]
    AF --> PF["Python Filter · school, title, location"]
    PF --> LLM["GPT-4o-mini Rerank · hard + soft"]
    LLM --> TOP["Top 10"]
```

**Stage details:**

| Stage | What | Latency | Candidates |
|---|---|---|---|
| Voyage-3 embed | Encode query (desc + criteria) into 1024-dim vector | ~200ms | 1 query |
| Turbopuffer ANN | Approximate nearest neighbor search over ~200K profiles | ~50ms | 200K to 200 |
| Turbopuffer attribute filter | Push degree type, field of study, start year filters into DB query (5 configs) | ~0ms (DB-side) | 200 to 50-150 |
| Python post-filter | Parse structured degree strings for undergrad location, school prestige, title match | ~1ms | 50-150 to 15-80 |
| LLM rerank | GPT-4o-mini scores each candidate on hard + soft criteria in batches of 5 | ~20-40s | 15-80 to 10 |

## Quick Start

**Prerequisites**: Python 3.9+, API keys for OpenAI, Voyage AI, and Turbopuffer.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export OPENAI_API_KEY="sk-..."
export VOYAGE_API_KEY="pa-..."
export TPUF_API_KEY="tpuf_..."

python main.py                              # Run all 10 configs
python main.py --config tax_lawyer.yml      # Run single config
python main.py --no-submit                  # Run without submitting to eval endpoint
```

## Results

### Run 1: Vector + strict filter + soft-only LLM rerank (46.7 avg)

| Config | **Run 1** | Hard Pass |
|---|---|---|
| Tax Lawyer | **82.7** | 100% |
| Junior Corporate Lawyer | **82.7** | 95% |
| Mechanical Engineers | **81.7** | 95% |
| Bankers | **73.7** | 90% |
| Radiology | **71.3** | 90% |
| Quantitative Finance | **43.0** | 70% |
| Biology Expert | **32.0** | 60% |
| Anthropology | **0.0** | 50% |
| Doctors (MD) | **0.0** | 63% |
| Mathematics PhD | **0.0** | 20% |
| **Average** | **46.7** | **73%** |

### Why the 0s

The eval endpoint uses an LLM judge for hard criteria, catching nuances that structured filters miss:

- **Anthropology (0.0):** 100% on "has PhD" but 0% on "PhD started within last 3 years." My filter had no recency check. The vector retrieval found anthropology PhDs, but none were recent enough.
- **Doctors MD (0.0):** 0% on "MD from top U.S. medical school." The deg_degrees field contains "MD" but no signal for school prestige ranking. Vector search returned MDs from non-US or non-top-tier schools.
- **Mathematics PhD (0.0):** 0% on "undergrad from US/UK/Canada." The hard criterion was about undergrad location, not PhD. My filter only checked degree type and field, not school geography.

### Root cause

Structured filters can enforce "has JD" or "field contains biology" but cannot evaluate "top U.S. medical school" or "PhD started recently." These require judgment, which is what the LLM reranker should handle.

### Run 2: Relaxed filters + LLM hard+soft rerank (52.1 avg)

Changes made:
1. **Richer query embedding:** Concatenated description + hard criteria + soft criteria before embedding, so vector retrieval pulls candidates matching the full intent, not just the role description.
2. **Relaxed hard filters:** Loosened degree matching (substring instead of exact), removed experience-year bucket checks. Filters now only remove obvious mismatches.
3. **LLM judges hard criteria:** Reranker prompt now includes hard criteria explicitly. Candidates failing any hard criterion get score 0. Candidates passing all hard criteria scored 1-10 on soft fit.
4. **Structured data in LLM prompt:** Passed degrees, experience, country, and summary to the LLM so it can evaluate criteria like school prestige and recency.

| Config | Run 1 | Run 2 | Hard Pass |
|---|---|---|---|
| Tax Lawyer | 82.7 | **80.0** | 100% |
| Junior Corporate Lawyer | 82.7 | **74.3** | 95% |
| Mechanical Engineers | 81.7 | **92.7** | 100% |
| Bankers | 73.7 | **81.3** | 95% |
| Radiology | 71.3 | **71.0** | 90% |
| Quantitative Finance | 43.0 | **34.0** | 70% |
| Biology Expert | 32.0 | **37.7** | 65% |
| Anthropology | 0.0 | **0.0** | 50% |
| Doctors (MD) | 0.0 | **8.0** | 73% |
| Mathematics PhD | 0.0 | **42.5** | 60% |
| **Average** | **46.7** | **52.1** | **80%** |

### Run 3: Turbopuffer attribute filters + post-filter on structured degree strings + LLM rerank (66.6 avg)

Changes made:
1. **Turbopuffer-level attribute filters:** For 5 configs, pushed degree type, field of study, and start year filters into the Turbopuffer query itself. This narrows retrieval at the database level before results hit Python.
2. **Structured degree string parsing:** For undergrad-location checks (math, biology) and school prestige (doctors), parsed the full `yrs_::school_::degree_::fos_::start_::end_` strings to verify specific degree entries, not just array membership.
3. **Top-school matching:** Built school name fragment lists for US/UK/CA undergrad institutions and top US medical schools to enforce location and prestige criteria in Python before LLM reranking.

| Config | Run 1 | Run 2 | **Run 3** | Hard Pass |
|---|---|---|---|---|
| Tax Lawyer | 82.7 | 80.0 | **80.0** | 100% |
| Junior Corporate Lawyer | 82.7 | 74.3 | **75.0** | 95% |
| Mechanical Engineers | 81.7 | 92.7 | **92.0** | 100% |
| Bankers | 73.7 | 81.3 | **81.3** | 95% |
| Radiology | 71.3 | 71.0 | **70.3** | 90% |
| Quantitative Finance | 43.0 | 34.0 | **65.7** | 90% |
| Biology Expert | 32.0 | 37.7 | **71.0** | 95% |
| Anthropology | 0.0 | 0.0 | **20.3** | 65% |
| Doctors (MD) | 0.0 | 8.0 | **36.5** | 83% |
| Mathematics PhD | 0.0 | 42.5 | **74.5** | 95% |
| **Average** | **46.7** | **52.1** | **66.6** | **91%** |

The biggest gains came from pushing hard criteria enforcement earlier in the pipeline. Configs where hard criteria map cleanly to structured fields (degree type, field of study, school name) improved the most. Anthropology remains the hardest because the eval's LLM judge determines PhD recency from the candidate's summary text, and most summaries don't state their enrollment year explicitly.

## Key Decisions

- **voyage-3 for query embedding.** Matches the corpus embedding model, ensuring vector space alignment.
- **Vector retrieval before filtering.** Narrowing 200K to 200 via ANN is milliseconds. Filtering 200 in memory is instant. Reversing the order risks either too-broad or too-narrow filter results.
- **GPT-4o-mini over GPT-4o.** 10x cheaper, sufficient accuracy for 0-10 relevance scoring.
- **Relaxed filters + strict LLM.** Better to let borderline candidates through to the LLM than to filter them out with brittle string matching.
- **Fallback to full set.** If filters return fewer than 15 candidates, skip filtering and let the LLM sort everything.
- **Batched LLM reranking.** Candidates scored in batches of 5 to stay within context limits while providing enough comparison context for relative scoring.

## Reducing Reranker Latency

The LLM reranker is the bottleneck. Currently ~50-150 candidates are scored in sequential batches of 5 via GPT-4o-mini API calls. For 10 configs, this means 100-300 serial API calls with 500ms-2s latency each.

**Immediate wins:**
1. **Async API calls.** Use `openai.AsyncClient` with `asyncio.gather()` to fire all batches concurrently. Reduces wall-clock time from O(n) to O(1) relative to batch count. Largest single improvement.
2. **Larger batch size.** Increase from 5 to 15-20 candidates per call. Cuts total API calls by 3-4x with minimal accuracy loss since GPT-4o-mini handles longer contexts well.
3. **Cache query embeddings.** The Voyage-3 embed call is repeated per run. Cache the 1024-dim vector keyed by query text hash.

**Architectural improvements:**

4. **Two-tier reranking.** Use Voyage's rerank endpoint (`vo.rerank(query, docs, model="rerank-2.5")`) as a fast intermediate pass to sort 200 candidates down to 20. Only send those 20 to GPT-4o-mini for nuanced hard/soft criteria judgment. Cross-encoder reranker: ~100ms for 200 candidates vs. ~30s for LLM scoring.
5. **Score only what matters.** Instead of sending full summaries (500+ chars), extract only the fields relevant to the config's criteria (degrees for academic roles, titles for professional roles). Reduces input tokens by 60-70%.
6. **Pointwise scoring.** Score each candidate independently (one LLM call per candidate) instead of listwise comparison. Enables full parallelism and eliminates batch-size constraints.

**At scale:**

7. **Pre-compute candidate feature vectors.** Extract structured features (degree type, school tier, years of experience) into a scoring matrix. Hard criteria become boolean filters on this matrix, no LLM needed. LLM reranking reserved for soft criteria only.
8. **Distill the reranker.** Fine-tune a small model (e.g., DeBERTa) on the LLM's scoring outputs to replace it for inference. Sub-10ms per candidate.

## What I Would Do With More Time

1. **Reciprocal Rank Fusion:** Combine vector ANN and BM25 results before filtering for better recall on exact keywords.
2. **Voyage cross-encoder reranking:** Faster intermediate rerank between filters and LLM scoring.
3. **Query expansion:** LLM-generated variant phrasings for multi-vector retrieval.
4. **Increase top_k to 500:** Wider net for configs where the target population is small.
5. **Generic filter-free pipeline:** Drop per-config filters and rely on enriched query embedding + LLM reranking for unseen role types.

## Project Structure

```
candidate-search-pipeline/
├── main.py              # Entry point: run all/single configs, submit results
├── pipeline.py          # 3-stage orchestration: embed, filter, rerank
├── embed.py             # Voyage-3 query embedding
├── tpuf_client.py       # Turbopuffer vector search client
├── filters.py           # Per-config hard-criteria filters
├── rerank.py            # GPT-4o-mini batch reranking
├── evaluate.py          # eval endpoint submission
├── configs/
│   └── queries.json     # 10 role configurations
├── results/             # Per-config evaluation results
└── requirements.txt
```

## License

Apache-2.0
