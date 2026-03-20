"""Turbopuffer client wrapper for querying the candidate collection."""

import os
from turbopuffer import Turbopuffer


TPUF_API_KEY = os.environ["TPUF_API_KEY"]
TPUF_REGION = os.environ.get("TPUF_REGION", "aws-us-west-2")
TPUF_NAMESPACE = os.environ.get("TPUF_NAMESPACE", "search-test-v4")

# All attributes we care about for filtering and re-ranking
INCLUDE_ATTRS = [
    "name", "country", "rerankSummary",
    "degrees", "experience",
    "deg_degrees", "deg_schools", "deg_fos",
    "deg_start_years", "deg_end_years", "deg_years",
    "exp_titles", "exp_companies",
    "exp_start_years", "exp_end_years", "exp_years",
]


_client = None


def get_client():
    """Return a cached TPUF client."""
    global _client
    if _client is None:
        _client = Turbopuffer(api_key=TPUF_API_KEY, region=TPUF_REGION)
    return _client


def get_namespace():
    """Return the TPUF namespace handle."""
    return get_client().namespace(TPUF_NAMESPACE)


def query_vector(vector, top_k=200, filters=None):
    """Query TPUF with a vector and optional filters.

    Returns list of dicts with _id and all included attributes.
    """
    ns = get_namespace()

    kwargs = {
        "rank_by": ("vector", "ANN", vector),
        "top_k": top_k,
        "include_attributes": INCLUDE_ATTRS,
    }
    if filters:
        kwargs["filters"] = filters

    result = ns.query(**kwargs)

    rows = []
    for row in result.rows:
        data = row.model_dump()
        entry = {"_id": data.get("id"), "dist": data.get("$dist")}
        for attr in INCLUDE_ATTRS:
            entry[attr] = data.get(attr)
        rows.append(entry)
    return rows
