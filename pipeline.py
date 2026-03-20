"""3-stage retrieval pipeline: embed -> filter -> rerank."""

from embed import embed_query
from tpuf_client import query_vector
from filters import apply_hard_filter
from rerank import rerank_candidates


def build_rich_query(config: dict) -> str:
    """Build a rich query string from description + criteria for better embedding."""
    parts = [config["description"]]
    parts.append("Required qualifications: " + "; ".join(config["hard_criteria"]))
    parts.append("Preferred qualifications: " + "; ".join(config["soft_criteria"]))
    return "\n".join(parts)


def run_pipeline(
    query_config: dict,
    top_k_retrieve: int = 200,
    top_k_final: int = 10,
) -> list[dict]:
    """Run the full pipeline for a single query config.

    Returns top_k_final candidates sorted by relevance.
    """
    title = query_config["title"]
    description = query_config["description"]
    config_path = query_config["config_path"]
    hard_criteria = query_config["hard_criteria"]
    soft_criteria = query_config["soft_criteria"]

    # Stage 1: Embed rich query and retrieve from TPUF
    rich_query = build_rich_query(query_config)
    print(f"[{title}] Stage 1: Embedding query and retrieving top {top_k_retrieve}...")
    query_vector_emb = embed_query(rich_query)
    candidates = query_vector(query_vector_emb, top_k=top_k_retrieve)
    print(f"  Retrieved {len(candidates)} candidates")

    # Stage 2: Light hard criteria pre-filter (relaxed, just to reduce noise)
    print(f"[{title}] Stage 2: Applying hard criteria filter...")
    filtered = apply_hard_filter(candidates, config_path)
    print(f"  {len(filtered)} candidates after filtering")

    # Stage 3: LLM re-ranking on BOTH hard and soft criteria
    print(f"[{title}] Stage 3: Re-ranking on hard + soft criteria...")
    reranked = rerank_candidates(
        filtered,
        description,
        hard_criteria,
        soft_criteria,
        top_k=top_k_final,
    )
    print(f"  Top {len(reranked)} candidates selected")

    return reranked
