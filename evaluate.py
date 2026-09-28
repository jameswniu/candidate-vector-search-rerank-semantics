"""Submit results to the evaluation endpoint.

The endpoint's URL and the email it authorizes are read from the EVAL_URL and
EVAL_AUTH_EMAIL environment variables when a slate is submitted, so a dry run
needs neither.
"""

import json
import os

import requests

ENV_VARS = ("EVAL_URL", "EVAL_AUTH_EMAIL")


def _endpoint() -> tuple[str, str]:
    """Return (url, email) from the environment, or stop with a message naming each unset variable."""
    missing = [name for name in ENV_VARS if not os.environ.get(name)]
    if missing:
        names = " and ".join(missing)
        verb = "is" if len(missing) == 1 else "are"
        raise SystemExit(f"{names} {verb} not set, so nothing was submitted. Export EVAL_URL (the evaluation "
                         "endpoint's URL) and EVAL_AUTH_EMAIL (the email it authorizes), then run again.")
    return os.environ["EVAL_URL"], os.environ["EVAL_AUTH_EMAIL"]


def submit(config_path: str, object_ids: list[str]) -> dict:
    """Submit ranked object_ids for a config and return the evaluation result."""
    url, email = _endpoint()
    resp = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": email,
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
