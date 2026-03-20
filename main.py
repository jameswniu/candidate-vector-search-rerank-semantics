"""Run the retrieval pipeline on all 10 query configs and submit for evaluation."""

import json
import sys
from pathlib import Path

from pipeline import run_pipeline
from evaluate import submit


CONFIGS_PATH = Path(__file__).parent / "configs" / "queries.json"
RESULTS_DIR = Path(__file__).parent / "results"


def load_configs():
    with open(CONFIGS_PATH) as f:
        return json.load(f)


def run_single(config, do_submit=True):
    """Run pipeline for one config, optionally submit for evaluation."""
    results = run_pipeline(config)
    object_ids = [r["_id"] for r in results]

    print(f"\n[{config['title']}] Top 10 IDs:")
    for i, r in enumerate(results):
        name = r.get("name", "?")
        score = r.get("llm_score", "?")
        print(f"  {i+1}. {r['_id']} ({name}) [score: {score}]")

    if do_submit:
        print(f"\n[{config['title']}] Submitting to eval endpoint...")
        try:
            eval_result = submit(config["config_path"], object_ids)
            print(f"  Result: {json.dumps(eval_result, indent=2)}")

            # Save result
            RESULTS_DIR.mkdir(exist_ok=True)
            result_file = RESULTS_DIR / f"{config['config_path'].replace('.yml', '.json')}"
            with open(result_file, "w") as f:
                json.dump({
                    "config": config["title"],
                    "config_path": config["config_path"],
                    "object_ids": object_ids,
                    "eval_result": eval_result,
                }, f, indent=2)
            return eval_result
        except Exception as e:
            print(f"  Eval error: {e}")
            return None
    return object_ids


def main():
    configs = load_configs()

    # Single config mode
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        target = sys.argv[idx + 1]
        config = next((c for c in configs if c["config_path"] == target), None)
        if not config:
            print(f"Config '{target}' not found")
            sys.exit(1)
        run_single(config)
        return

    # Run all configs
    do_submit = "--submit" in sys.argv or "--no-submit" not in sys.argv
    all_results = {}

    for config in configs:
        print(f"\n{'='*60}")
        print(f"Processing: {config['title']}")
        print(f"{'='*60}")
        result = run_single(config, do_submit=do_submit)
        all_results[config["title"]] = result

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for title, result in all_results.items():
        print(f"  {title}: {result}")


if __name__ == "__main__":
    main()
