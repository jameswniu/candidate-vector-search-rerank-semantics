"""Voyage-3 query embedding."""

import os
import voyageai


VOYAGE_API_KEY = os.environ["VOYAGE_API_KEY"]


def embed_query(text: str) -> list[float]:
    """Embed a query string using Voyage-3. Returns 1024-dim vector."""
    vo = voyageai.Client(api_key=VOYAGE_API_KEY)
    result = vo.embed([text], model="voyage-3", input_type="query")
    return result.embeddings[0]
