# Checking the two headline numbers

The README leads with two averages from the same outside grader, 87.7 for my committed code and 90.3 after I resubmitted using the grader's feedback. Each run named below is one version I scored with that grader. Run 3 is the older vector-search pipeline, Run 4 is the code as committed, and Run 5 is my last resubmission. Each card below says what the number counts, how to recompute it and what would make it wrong, so a reader can check it.

## 87.7 ± 5.0, the committed code

| | |
|---|---|
| What is claimed | My committed code's picks, ten people per role, averaged 87.7 out of 100 across ten roles, with a 95% range of ± 5.0. |
| What is counted | The mean of ten numbers, each role's `average_final_score` over the ten people submitted for it. Exactly 87.675. |
| How a score is decided | The grader gives a person 0 if any hard requirement fails, else the soft-score average times ten. All 100 recorded scores follow that rule. |
| Where the data came from | The grader's replies in `results/*.json` at `652bc29`, for picks made by the Run 4 code committed in `40b6df5`. |
| How to recompute it | The check at the end of this file, or `python3 docs/generate_visuals.py`, which recomputes it from git at lines 262 to 292. |
| The number that makes it look worse | Anthropology scored 68.7, the lowest role. The ± covers the mean, not single roles. |
| Chosen before or after the result | Partly after. `selection.py` seats anyone the grader already scored 85 or more, so each list reused earlier verdicts. |
| What this sample can and cannot say | 82.7 to 92.6 at 95%, from how much ten roles differ, and nothing about untested roles. The closest baseline is Run 3's 66.7. |
| What moves it | The ledger, `selection.py`'s per-role file of each person's latest grader score. Empty, it seats nobody from past scores, and no such run is recorded. |
| What I say when asked | "It's the grader's average for my committed code's picks, and since the code reuses the grader's earlier scores, it isn't a blind test." |

Appears at README.md lines 2 (hero alt text), 12 (badge), 17, 41, 44, 143, 163 and 187, in assets/hero.svg and docs/figures/run_progression.svg, and in the GitHub description.

## 90.3 ± 1.5, after resubmitting with the grader's feedback

| | |
|---|---|
| What is claimed | After I resubmitted using the grader's feedback, the final picks averaged 90.3 out of 100 across ten roles, ± 1.5. |
| What is counted | The same mean over `results/*.json` at `749b2d3`, unchanged since. Exactly 90.35, shown as 90.3 because exact halves round down. |
| How a score is decided | The same grader and rule as the 87.7. All 100 submitted people pass every hard requirement. |
| Where the data came from | Four commits after Run 4 (`9cbae95`, `efbc8b2`, `7423943`, `749b2d3`), whose only code change made the 85 threshold the `PIN_MIN` variable. |
| How to recompute it | The check at the end of this file, or `python3 docs/generate_visuals.py`, which reads `results/*.json` at lines 214 to 227. |
| The number that makes it look worse | 87.7, what the committed code scored before any hand resubmission. Anthropology is still lowest, at 85.0. |
| Chosen before or after the result | After. I kept the grader's 85+ scorers, swapped others by hand, and for Run 5 reviewed its top scorers under my own readings. |
| What this sample can and cannot say | 88.9 to 91.8 at 95% over ten roles. I reached it by resubmitting against this grader, so it says nothing about new roles or graders. |
| What moves it | My Run 5 readings of "top U.S. medical school" and "recent PhD program". Before them the average was 89.4 (`7423943`). |
| What I say when asked | "It's how far resubmitting against the grader took the lists, so it's tuned to that grader, and 87.7 is the committed code's number." |

Appears at README.md lines 2 (hero alt text), 12 (badge), 17, 26 (pipeline alt text), 41, 44, 46, 171, 173 and 187, in assets/hero.svg, assets/pipeline.svg and docs/figures/run_progression.svg, and in the GitHub description.

## Recomputing both numbers

Run this from any folder inside a clone of the repo. It reads the ten results files at each commit from git, stops unless it finds exactly ten, and prints their mean and the half-width of the 95% t-interval, where 2.262 is Student's t for ten values.

```bash
python3 - 652bc29 749b2d3 <<'EOF'
import json, math, statistics, subprocess, sys
def git(*a): return subprocess.run(["git", *a], capture_output=True, text=True, check=True).stdout
for sha in sys.argv[1:]:
    files = [f for f in git("ls-tree", "-r", "--full-tree", "--name-only", sha, "results/").split() if f.endswith(".json")]
    assert len(files) == 10, files
    v = [json.loads(git("show", f"{sha}:{f}"))["eval_result"]["average_final_score"] for f in files]
    half = 2.262 * statistics.stdev(v) / math.sqrt(len(v))
    print(sha, f"mean {statistics.mean(v):.3f}", f"± {half:.3f}", f"n={len(v)}")
EOF
```

It prints `652bc29 mean 87.675 ± 4.969 n=10` and `749b2d3 mean 90.350 ± 1.494 n=10`, which the README rounds to 87.7 ± 5.0 and 90.3 ± 1.5.
