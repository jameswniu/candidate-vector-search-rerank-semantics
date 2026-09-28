<p align="center">
  <img src="assets/hero.svg" alt="Candidate search over a Turbopuffer database of profiles. The pipeline as committed averaged 87.7 ± 5.0 across 10 configs (Run 4). Grader-guided resubmission raised the average to 90.3 ± 1.5 (Run 5). Each ± is a 95% t-interval for the mean of these ten roles, with no claim about unseen roles. In the final submitted slates, all 10 configs pass every hard criterion, all 10 score 80 or above, 8 score 90 or above, and there are 0 hard failures in 100 recorded seats." width="100%">
</p>

<div align="center">

<h1>Candidate Search for Ten Hiring Roles</h1>

<img alt="python 3.9+" src="https://img.shields.io/badge/python-3.9%2B-dfe3e0?style=flat-square&labelColor=0c1013">
<img alt="judge model GPT-4o-mini" src="https://img.shields.io/static/v1?label=judge%20model&message=GPT-4o-mini&color=59636e&style=flat-square&labelColor=0c1013">
<img alt="database Turbopuffer" src="https://img.shields.io/static/v1?label=database&message=Turbopuffer&color=59636e&style=flat-square&labelColor=0c1013">
<img alt="grader score 87.7 as committed, 90.3 after resubmitting" src="https://img.shields.io/static/v1?label=grader%20score&message=87.7%20as%20committed%2C%2090.3%20after%20resubmitting&color=59636e&style=flat-square&labelColor=0c1013">
<img alt="license Apache-2.0" src="https://img.shields.io/static/v1?label=license&message=Apache-2.0&color=59636e&style=flat-square&labelColor=0c1013">

</div>

I built a candidate search system that selects ten people per hiring role from roughly 200,000 profiles. The core challenge is that ranking by textual similarity to a job description surfaces people who read close to the role but miss a must-have, such as an MD from a top U.S. medical school, and a hiring manager can't use them. Across ten roles, an outside grader scored the lists from my committed code at 87.7 out of 100 on average, rising to 90.3 after I resubmitted using its feedback, with every must-have met in both. Both numbers depend on that grader, since my code seats people it had already scored 85 or more and I reached the 90.3 by resubmitting against its scores, and ten roles is too small a sample to claim it generalizes to unseen ones.

How I computed each number, and what would make it wrong, is in [docs/REFEREE.md](docs/REFEREE.md).

## How it works

Candidate profiles are stored in Turbopuffer, a hosted vector database. Each of the ten roles is a config, an entry in `configs/queries.json` that lists hard requirements, the must-haves a candidate cannot lack (a JD and three years of practice for Tax Lawyer), and soft preferences that are scored for fit (such as IRS audit experience). The code works through one role at a time, in four steps.

<p align="center">
  <img src="assets/pipeline.svg" alt="Candidate search pipeline over a Turbopuffer database, in five stages. Scan pages in id order through every profile that matches the role's attribute filter. Prescreen checks degree, school, field and dates, ranks by keywords and keeps 250 to 550 candidates per role. Judge has GPT-4o-mini score hard and soft criteria from the profile text alone, without live scores. Select seats candidates the live grader already scored 85 or above first, then judged hard passes. Submit sends ten candidates per role to the live grader. Outputs are results/*.json, a submission ledger that drops hard failures and pins 85+ scorers, and a run table with averages from 52.1 to 90.3." width="100%">
</p>

1. `pool.py` scans the database. Each role has an attribute filter, a condition Turbopuffer applies to a structured field such as degree type, field of study or country, and the scan pages through every profile that matches it, in id order, up to 100,000 rows.
2. `pool.py` then prescreens, a rule-based cut made before any model reads a profile. Five roles first check school names in the parsed degree entries, before fetching full records. Doctors need an MD from an elite school, Mathematics and Biology a bachelor's from the U.S., U.K. or Canada, Quantitative Finance an MBA from one of the seven schools `pool.py` lists as the M7, and Bankers a U.S. MBA. Every role then keeps the profiles that pass its own check on degree entries, summary text or both, ranks them by keyword counts in the summary, and keeps the top 250 to 550 as its pool. These school lists, keyword checks and caps can drop qualified people.
3. `judge.py` is the LLM judge, a language model that scores each pooled profile against the role, one profile per call. It uses GPT-4o-mini unless `JUDGE_MODEL` names another model. It reads only the profile text (the `rerankSummary` field), which is what I assume the grader reads, plus per-role calibration notes drawn from the grader's earlier verdicts, such as which schools pass as top. It marks each hard requirement pass or fail, scores each soft preference 0 to 10, and predicts 0 on any hard failure, otherwise the soft average times ten, the same formula the grader uses. It never sees a grader score.
4. `selection.py` picks the ten to submit for a role, its slate, and sends them to the grader, whose reply is the recorded score. It keeps a ledger, a per-role file holding the grader's latest score for everyone it has scored and whether it ever failed them on a hard requirement, seeded from the committed `results/<config>.json`. Anyone the grader failed on a hard requirement is out for good, and IDs named with `--exclude` are left out of that run. Anyone the grader already scored 85 or above (the `PIN_MIN` default) is pinned, meaning seated first, IDs named with `--include` come next, and judged candidates who pass every hard requirement fill the remaining seats in order of predicted score. Pinned and `--include` candidates skip the local hard-requirement check. It then writes `results/<config>.json`, archives the reply, and folds each outcome back into the ledger.

The pipeline in `main.py` is my older one, as it stood at Run 3, where each run is one version of the pipeline scored by the grader (listed under [Results details](#results-details)). It embeds the role text with Voyage-3, converting it into a vector, a list of numbers that encodes meaning. It then pulls the 200 nearest profiles from Turbopuffer with an approximate nearest-neighbor (ANN) search, which finds close matches without comparing against every record, filters them in Python, and has GPT-4o-mini rerank the survivors, re-sorting them by fit in batches of five. This pipeline produced none of the Run 4 and Run 5 results.

The two pipelines drop candidates in different places. In the vector pipeline, Run 3 moved some filters into the ANN query itself, and the Python filters stayed relaxed (`filters.py`) so a borderline candidate still reached the LLM. When fewer than 15 candidates survived a Python filter, it fell back to the results from before that filter. The final pipeline embeds nothing. It applies the attribute filter inside the database scan, then cuts the pool with strict school lists, keyword checks and the 250 to 550 cap before any LLM call, with no fallback. `judge.py` scores one candidate per call, up to 24 at once, and caches each judgment. GPT-4o-mini is the default model in both pipelines.

## Results

<p align="center">
  <img src="docs/figures/run_progression.svg" alt="Average final score by run. Runs 2 and 3 retrieved a vector top 200 and averaged 52.1 and 66.7. Run 4, the pipeline as committed with exhaustive scans and an LLM judge, averaged 87.7. Grader-guided resubmission then reached 89.4, and Run 5 reached 90.3. Run 1 has no results file and is not drawn." width="100%">
</p>

Run 4 (`40b6df5`) scans every profile that matches the role's attribute filter instead of taking the 200 nearest by vector similarity, adds the per-profile LLM judge, and keeps a ledger of the grader's verdicts. Across ten roles it recorded an average of 87.7 ± 5.0 with every hard requirement passing (`652bc29`), up from 66.7 in Run 3. I then kept resubmitting against the grader, keeping the people it had already scored 85 or above and swapping others in or out by hand, which brought the average to 89.4 and then 90.3 ± 1.5 (`749b2d3`). For that final step, Run 5, I picked the Doctors and Anthropology slates under my own readings of two hard requirements. I counted a wider set of U.S. medical schools as top, and I counted current doctoral students, ABD (all but dissertation) included, and 2023-or-later graduates as being in a recent PhD program. Neither reading, nor that hand selection, is in the committed code.

Each ± is a 95% t-interval for the mean, a range computed from how much the ten roles' scores differ from each other, and it says nothing about roles I did not test. Every average here is the mean of the ten roles' `average_final_score` in `results/*.json` at the named commit, rounded to one decimal with exact halves rounded down, so Run 2's 52.15 shows as 52.1 and Run 5's 90.35 as 90.3. `python3 docs/generate_visuals.py` redraws the four figures from those files and git history, and stops if a figure's number disagrees with them.

What changed in each run, with every role's score, is under [Results details](#results-details).

## Quick Start

You need Python 3.9+, API keys for OpenAI and Turbopuffer, a Voyage AI key for `main.py` only, and the evaluation endpoint's URL and the email it authorizes. `evaluate.py` reads `EVAL_URL` and `EVAL_AUTH_EMAIL` only when it submits, so a dry run needs neither.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export OPENAI_API_KEY="sk-..."
export TPUF_API_KEY="tpuf_..."
export VOYAGE_API_KEY="pa-..."   # main.py only
export EVAL_URL="<evaluation endpoint URL>"
export EVAL_AUTH_EMAIL="<email the endpoint authorizes>"
```

The Run 4 pipeline runs one config at a time, in this order. `pool.py` scans, prescreens and caches the pool, and with no argument it builds all ten. `judge.py` judges every pooled candidate. `selection.py --dry` prints the ten it would submit and submits nothing, and without `--dry` it submits them and overwrites `results/doctors_md.json`. `selection.py` also seeds its ledger from the committed `results/<config>.json`, so on a fresh clone it pins that file's 85+ scorers. `pool.py` and `judge.py` reuse whatever is already in `cache/`.

```bash
python pool.py doctors_md.yml             # scan, prescreen, cache
python judge.py doctors_md.yml            # judge the pool
python selection.py doctors_md.yml --dry  # show the ten, submit none
python selection.py doctors_md.yml        # submit, overwrite results
```

`python main.py` runs the Run 3 vector pipeline, which produced none of the recorded Run 4 and Run 5 results. With `--no-submit` it runs all ten configs and submits nothing. Without it, it submits all ten and overwrites every `results/*.json`. With `--config` it runs one config and always submits and overwrites that config's results file, even when `--no-submit` is given.

```bash
python main.py --no-submit              # all 10, nothing submitted
python main.py                          # submits, overwrites results
python main.py --config tax_lawyer.yml  # always submits
```

## Results details

Each run below says what changed, and each recorded run shows the grader's score for every role at the named commit.

### Run 1, not in the repo

Run 1 predates the first commit, so neither its code nor its results are in the repo, and I leave its numbers out.

### Run 2, relaxed filters and an LLM that checks hard criteria (52.1 avg)

Structured filters can enforce "has JD" or "field contains biology" but cannot evaluate "top U.S. medical school" or "PhD started recently", so Run 2 gave that judgment to the LLM. Its results are recorded in `0341cfa`, and its pipeline worked this way.

1. The query embedding concatenates the description, hard criteria and soft criteria, so retrieval matches the whole role spec.
2. The hard filters match degrees by substring and check no experience years, so they remove only obvious mismatches.
3. The reranker prompt lists the hard criteria, scores any candidate who fails one at 0, and scores the rest 1 to 10 on soft fit.
4. The prompt carries degrees, experience, country and the summary, so the LLM can judge criteria like school prestige and recency.

| Config | **Run 2** | Hard Pass |
|---|---|---|
| Tax Lawyer | **80.0** | 100% |
| Junior Corporate Lawyer | **74.3** | 95% |
| Mechanical Engineers | **92.7** | 100% |
| Bankers | **81.3** | 95% |
| Radiology | **71.0** | 90% |
| Quantitative Finance | **34.0** | 70% |
| Biology Expert | **37.7** | 65% |
| Anthropology | **0.0** | 50% |
| Doctors (MD) | **8.0** | 70% |
| Mathematics PhD | **42.5** | 65% |
| **Average** | **52.1** | **80%** |

The grader uses an LLM judge for hard criteria, and Run 2's recorded slates show what my filters still missed.

- Anthropology scored 0.0, with 100% on "has PhD" and 0% on "PhD started within the last 3 years". My filter had no recency check, and vector retrieval found anthropology PhDs, none of them recent enough.
- Doctors scored 8.0, with 10% on "MD from a top U.S. medical school". The `deg_degrees` field says "MD" and carries no signal for school prestige.
- Mathematics PhD scored 42.5, with 50% on "undergrad from the U.S., U.K. or Canada". That criterion is about undergraduate location, and my filter checked only degree type and field.

### Run 3, database filters and parsed degree strings (66.7 avg)

Run 3 (`170b1a9`) kept the vector top 200 and moved hard-criteria checks earlier.

1. For five configs, degree type, field of study and, for Anthropology, start year became Turbopuffer attribute filters inside the ANN query, so the database narrows retrieval before results reach Python.
2. For undergraduate location (Mathematics, Biology) and school prestige (Doctors), the pipeline parses the full `yrs_::school_::degree_::fos_::start_::end_` strings to check specific degree entries.
3. School-name fragment lists for U.S., U.K. and Canadian undergraduate institutions and for top U.S. medical schools enforce location and prestige in Python before the LLM rerank. The check is skipped when fewer than 15 candidates survive it.

| Config | Run 2 | **Run 3** | Hard Pass |
|---|---|---|---|
| Tax Lawyer | 80.0 | **80.0** | 100% |
| Junior Corporate Lawyer | 74.3 | **75.0** | 95% |
| Mechanical Engineers | 92.7 | **92.0** | 100% |
| Bankers | 81.3 | **81.3** | 95% |
| Radiology | 71.0 | **70.3** | 90% |
| Quantitative Finance | 34.0 | **65.7** | 90% |
| Biology Expert | 37.7 | **71.0** | 95% |
| Anthropology | 0.0 | **20.3** | 65% |
| Doctors (MD) | 8.0 | **36.5** | 83% |
| Mathematics PhD | 42.5 | **74.5** | 95% |
| **Average** | **52.1** | **66.7** | **91%** |

The biggest gains came from enforcing hard criteria earlier. Configs whose hard criteria map cleanly to structured fields (degree type, field of study, school name) improved the most. Anthropology stayed the hardest, at 20.3. My read is that the grader's judge looks for PhD recency in the summary text, and most summaries don't state an enrollment year.

### Run 4, exhaustive scans, an LLM judge and a submission ledger (87.7 avg)

Run 3 still lost points in three ways. ANN retrieval dropped qualified candidates that a top-200 vector neighborhood missed. My reranker read structured fields that I assume the grader's judge never sees, so we disagreed about who passes. And each submission threw away what earlier submissions had shown. Run 4 (code in `40b6df5`, results in `652bc29`) rebuilt the pipeline around those three problems.

1. Exhaustive structured scans replaced ANN for candidate generation. Paginated, id-ordered scans with Turbopuffer attribute filters return every row that matches the filter, and the degree lists, school lists, keyword checks and caps after the scan limit recall against the hard criteria. Soft-fit order comes from keyword counts and then the judge's predicted score. Scan sizes and timings are not recorded.
2. The local judge uses the grader's formula, 0 on any hard failure and otherwise the soft mean times ten. It reads only `rerankSummary`, ignores the structured fields, and carries per-config calibration notes learned from earlier verdicts, such as which schools pass as "top", that M7 is literal, and that a residency without a listed MD fails. A general prompt rule fails undated experience on duration criteria, and GPT-4o-mini runs over every pooled candidate.
3. A submission ledger feeds the grader's verdicts back into selection. Each submission's per-candidate outcomes fold into a per-config ledger that starts from the recorded results file. A candidate the grader hard-failed is dropped for good, and anyone it scored 85 or above is pinned into the next slate ahead of the judge's picks, without a local hard-criteria check. So every Run 4 and Run 5 slate was chosen partly by the grader's own earlier scores, and each recorded number is the grader's score for the ten I actually submitted.

| Config | Run 3 | **Run 4** | Hard Pass |
|---|---|---|---|
| Radiology | 70.3 | **92.3** | 100% |
| Mechanical Engineers | 92.0 | **92.0** | 100% |
| Junior Corporate Lawyer | 75.0 | **91.3** | 100% |
| Bankers | 81.3 | **90.3** | 100% |
| Quantitative Finance | 65.7 | **90.2** | 100% |
| Mathematics PhD | 74.5 | **89.7** | 100% |
| Tax Lawyer | 80.0 | **88.3** | 100% |
| Doctors (MD) | 36.5 | **87.0** | 100% |
| Biology Expert | 71.0 | **86.8** | 100% |
| Anthropology | 20.3 | **68.7** | 100% |
| **Average** | **66.7** | **87.7** | **100%** |

Five of ten configs finish at 90 or above, nine at 85 or above, and every hard criterion passes at 100%. Run 3's three weakest configs gained the most, Doctors from 36.5 to 87.0, Anthropology from 20.3 to 68.7, and Quantitative Finance from 65.7 to 90.2.

### Grader-guided resubmission (89.4 avg)

After Run 4 I kept resubmitting with the grader in the loop. Three commits (`9cbae95`, `efbc8b2`, `7423943`) recorded the resubmitted slates, which kept candidates the grader had already scored 85 or above and swapped others in or out by hand. Their only code change turned the 85 pin threshold into the `PIN_MIN` environment variable. The average reached 89.4, and the table under Run 5 shows each role.

### Run 5, Doctors and Anthropology picked under my own reading standards (90.3 avg)

Run 5 (`749b2d3`) changed no code. It resubmitted only the Doctors and Anthropology slates, which I picked under the two reading standards below. Doctors rose from 88.0 to 89.5 and Anthropology from 77.2 to 85.0, and the average reached 90.3.

| Config | Run 4 | Resubmitted | **Run 5** | Hard Pass |
|---|---|---|---|---|
| Radiology | 92.3 | 92.3 | **92.3** | 100% |
| Mechanical Engineers | 92.0 | 92.0 | **92.0** | 100% |
| Tax Lawyer | 88.3 | 91.8 | **91.8** | 100% |
| Junior Corporate Lawyer | 91.3 | 91.3 | **91.3** | 100% |
| Mathematics PhD | 89.7 | 90.5 | **90.5** | 100% |
| Biology Expert | 86.8 | 90.5 | **90.5** | 100% |
| Bankers | 90.3 | 90.3 | **90.3** | 100% |
| Quantitative Finance | 90.2 | 90.2 | **90.2** | 100% |
| Doctors (MD) | 87.0 | 88.0 | **89.5** | 100% |
| Anthropology | 68.7 | 77.2 | **85.0** | 100% |
| **Average** | **87.7** | **89.4** | **90.3** | **100%** |

<p align="center">
  <img src="docs/figures/config_scores.svg" alt="Recorded eval scores of the final submitted slates, after grader-guided resubmission, for all ten role configs, from results/. Eight of ten score 90 or above, all ten score 80 or above, and every hard criterion passes at 100 percent." width="100%">
</p>

The final slates have every config at 80 or above, eight at 90 or above, and every hard criterion passing at 100%, with 0 hard failures in 100 seats.

### The Run 5 reading standards, which are not in the committed code

For Run 5 I read two hard criteria the way I believe the roles mean them. These readings live only in this README, and the committed `pool.py` and `judge.py` read both criteria differently.

- I read "top U.S. medical school" as the elite research tier plus schools that recognized rankings place in the top 20 to 25 for research (UT Southwestern, Pittsburgh, UNC Chapel Hill, University of Washington, Case Western), with the MD itself, not a residency or fellowship, from a qualifying school. The committed school list in `pool.py` and the Doctors note in `judge.py` pass only their elite schools, and the note fails University of Washington by name. Three of the final ten Doctors seats hold MDs from UT Southwestern or UNC Chapel Hill.
- I read "recent PhD program" as a current or recently completed doctoral researcher in anthropology, sociology or economics. Current enrollment (candidate, ABD, Nth-year, dissertating) or a PhD completed in 2023 or later passes. A PhD completed in 2022 or earlier with no current enrollment fails, as do adjacent fields (area studies, education, psychology) and non-doctoral profiles. The committed Anthropology note in `judge.py` passes only dated evidence of a 2023 to 2026 program start or first- and second-year phrasing.

The candidates I reviewed under these readings were the ones the live grader had already scored highest, and no code or output from that review is committed.

## What limits it and what I have not built

Past the attribute filter, exact degree-name lists, school lists, keyword checks and the pool cap limit recall, meaning some qualified candidates are dropped before the judge ever sees them. No stage timings are recorded, so I make no speed claims. `pool.py` and `judge.py` already cache pools and judgments, and `judge.py` issues its LLM calls concurrently, while the `main.py` reranker still makes its batch calls one after another.

I have not built a cross-encoder pass, meaning a model that reads the role and one profile together and returns a single relevance score, or a judge that receives only the fields each requirement needs, so I give no savings numbers for either. For larger scale I would turn the hard requirements into yes-or-no checks over facts extracted from each profile in advance, with no LLM call, and distill the soft scorer into a small fine-tuned model trained to reproduce the LLM's scores, and neither is built. BM25 rank fusion, which merges in a classic keyword-match ranking, is not built either, and neither is LLM query expansion, where a model adds related search terms, or a filter-free pipeline for role types the system has not seen.

## Files

```
candidate-vector-search-rerank-semantics/
├── pool.py              # Database scans and per-role candidate pools
├── judge.py             # LLM judge with the grader's formula and per-role calibration notes
├── selection.py         # Picks each slate, submits it and keeps the ledger
├── evaluate.py          # Sends a slate to the grader (reads EVAL_URL and EVAL_AUTH_EMAIL)
├── main.py              # Runs the Run 3 vector pipeline for all or one role and submits
├── pipeline.py          # Run 3 pipeline: embed, filter, rerank
├── embed.py             # Voyage-3 query embedding (Run 3 pipeline only)
├── tpuf_client.py       # Turbopuffer client (ANN query for main.py, database handle for pool.py)
├── filters.py           # Per-role hard-requirement filters (Run 3 pipeline)
├── rerank.py            # GPT-4o-mini batch reranking (Run 3 pipeline)
├── configs/
│   └── queries.json     # The 10 role configs
├── results/             # The grader's reply per role (latest recorded run)
├── docs/                # REFEREE.md, and generate_visuals.py, which draws the figures from results/ and git history
└── requirements.txt
```

The code is licensed under Apache-2.0 (see `LICENSE`).
