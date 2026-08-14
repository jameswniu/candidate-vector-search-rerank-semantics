"""Pick the 10 submission candidates for a config, submit, and reconcile.

Selection blends two signal sources:
- The ledger: per-candidate ground truth from prior eval submissions. A
  candidate the real judge hard-failed is blacklisted permanently; one that
  scored 85+ is pinned ahead of any prediction.
- Local judgments (cache/judgments-<config>.json from judge.py or an
  external harness): candidates predicted to pass every hard criterion,
  ranked by predicted final score.

Every submission is archived under results-history/ and folded back into the
ledger, so each iteration only improves the empirical picture.
"""

from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from evaluate import submit
from judge import get_config

BASE = Path(__file__).parent
CACHE_DIR = BASE / "cache"
LEDGER_DIR = BASE / "ledger"
RESULTS_DIR = BASE / "results"
HISTORY_DIR = BASE / "results-history"


def _ledger_file(config_path: str) -> Path:
    return LEDGER_DIR / f"{config_path.replace('.yml', '')}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fold(ledger: dict, eval_result: dict):
    """Fold one eval response's per-candidate outcomes into the ledger.

    hard_fail is sticky: once the real judge fails a candidate on any hard
    criterion, the candidate stays blacklisted even if a later (noisy) run
    passes them.
    """
    for r in eval_result.get("individual_results", []):
        cid = (r.get("raw_data") or {}).get("_id")
        if not cid:
            continue
        failed = any(not h.get("passes", False) for h in r.get("hard_scores", []))
        prior = ledger.get(cid, {})
        ledger[cid] = {
            "final": r.get("final_score"),
            "hard_fail": bool(prior.get("hard_fail")) or failed,
            "last": _now(),
        }


def seed_ledger(config_path: str) -> dict:
    LEDGER_DIR.mkdir(exist_ok=True)
    lf = _ledger_file(config_path)
    if lf.exists():
        return json.loads(lf.read_text())
    ledger: dict = {}
    seed_file = RESULTS_DIR / f"{config_path.replace('.yml', '')}.json"
    if seed_file.exists():
        prior = json.loads(seed_file.read_text())
        _fold(ledger, prior.get("eval_result") or {})
    lf.write_text(json.dumps(ledger, indent=2))
    return ledger


def update_ledger(config_path: str, eval_result: dict) -> dict:
    ledger = seed_ledger(config_path)
    _fold(ledger, eval_result)
    _ledger_file(config_path).write_text(json.dumps(ledger, indent=2))
    return ledger


def choose(config_path: str, exclude: set[str], include: list[str] | None = None) -> list[dict]:
    stem = config_path.replace(".yml", "")
    ledger = seed_ledger(config_path)
    judgments = json.loads((CACHE_DIR / f"judgments-{stem}.json").read_text())
    pool = {c["_id"]: c for c in json.loads((CACHE_DIR / f"pool-{stem}.json").read_text())}

    blacklist = {cid for cid, e in ledger.items() if e.get("hard_fail")} | exclude
    pins = sorted(
        (cid for cid, e in ledger.items()
         if cid not in blacklist and (e.get("final") or 0) >= 85),
        key=lambda cid: ledger[cid]["final"], reverse=True)
    forced = [cid for cid in (include or []) if cid not in blacklist]
    eligible = sorted(
        (cid for cid, j in judgments.items()
         if cid not in blacklist and all(h["passes"] for h in j["hard"])),
        key=lambda cid: judgments[cid]["predicted"], reverse=True)

    chosen, seen = [], set()
    for cid in list(pins) + forced + eligible:
        if cid in seen:
            continue
        seen.add(cid)
        entry = {
            "id": cid,
            "name": pool.get(cid, {}).get("name", "?"),
            "pinned": cid in pins,
            "predicted": judgments.get(cid, {}).get("predicted"),
            "actual": ledger.get(cid, {}).get("final"),
        }
        chosen.append(entry)
        if len(chosen) == 10:
            break
    return chosen


def reconcile(chosen: list[dict], eval_result: dict):
    print(f"\n  average_final_score: {eval_result.get('average_final_score'):.1f}")
    for h in eval_result.get("average_hard_scores", []):
        print(f"  HARD {h['criteria_name']}: {h['pass_rate']*100:.0f}%")
    for s in eval_result.get("average_soft_scores", []):
        print(f"  SOFT {s['criteria_name']}: {s['average_score']:.1f}")
    actual_by_id = {}
    fails_by_id = {}
    for r in eval_result.get("individual_results", []):
        cid = (r.get("raw_data") or {}).get("_id")
        actual_by_id[cid] = r.get("final_score")
        fails_by_id[cid] = [(h["criteria_name"], (h.get("reasoning") or "")[:200])
                            for h in r.get("hard_scores", []) if not h.get("passes")]
    print("\n  predicted vs actual:")
    for c in chosen:
        actual = actual_by_id.get(c["id"])
        tag = "PIN" if c["pinned"] else "new"
        pred = c["predicted"] if c["predicted"] is not None else c["actual"]
        print(f"    [{tag}] {c['name'][:30]:30s} pred {pred} -> actual {actual}")
        for crit, why in fails_by_id.get(c["id"], []):
            print(f"          HARD FAIL {crit}: {why}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python selection.py <config.yml> [--dry] [--exclude id1,id2]")
        sys.exit(1)
    config_path = sys.argv[1]
    dry = "--dry" in sys.argv
    exclude: set[str] = set()
    if "--exclude" in sys.argv:
        exclude = set(sys.argv[sys.argv.index("--exclude") + 1].split(","))
    include: list[str] = []
    if "--include" in sys.argv:
        include = sys.argv[sys.argv.index("--include") + 1].split(",")

    config = get_config(config_path)
    chosen = choose(config_path, exclude, include)
    print(f"[{config_path}] selection:")
    for i, c in enumerate(chosen):
        tag = "PIN" if c["pinned"] else "new"
        score = c["actual"] if c["pinned"] else c["predicted"]
        print(f"  {i+1:2d}. [{tag}] {score} {c['id']} {c['name'][:40]}")
    if len(chosen) < 10:
        print(f"  WARNING: only {len(chosen)} candidates available")
    if dry:
        return

    ids = [c["id"] for c in chosen]
    eval_result = submit(config_path, ids)

    stem = config_path.replace(".yml", "")
    HISTORY_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (HISTORY_DIR / f"{stem}-{stamp}.json").write_text(json.dumps(eval_result, indent=2))
    (RESULTS_DIR / f"{stem}.json").write_text(json.dumps({
        "config": config["title"],
        "config_path": config_path,
        "object_ids": ids,
        "eval_result": eval_result,
    }, indent=2))
    update_ledger(config_path, eval_result)
    reconcile(chosen, eval_result)


if __name__ == "__main__":
    main()
