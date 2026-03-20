"""Submit results to the grader evaluation endpoint."""

import requests
import json


EVAL_URL = "https://example.invalid/evaluate"
AUTH_EMAIL = "you@example.com"


def submit(config_path: str, object_ids: list[str]) -> dict:
    """Submit ranked object_ids for a config and return the evaluation result."""
    resp = requests.post(
        EVAL_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": AUTH_EMAIL,
        },
        json={
            "config_path": config_path,
            "object_ids": object_ids[:10],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python evaluate.py <config_path> <id1,id2,...>")
        sys.exit(1)
    config = sys.argv[1]
    ids = sys.argv[2].split(",")
    result = submit(config, ids)
    print(json.dumps(result, indent=2))
