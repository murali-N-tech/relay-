"""
app/retrieval/reranking.py
Re-ranking engine using query term proximity, n-gram lexical coverage,
and Reciprocal Rank Fusion (RRF) to re-order candidate passages.
"""

import math
from typing import List, Tuple
from app.retrieval.chunking import TextChunk
from app.retrieval.indexing import tokenize

def compute_density_score(query_terms: List[str], chunk_terms: List[str]) -> float:
    """Computes density and bigram co-occurrence score."""
    if not query_terms or not chunk_terms:
        return 0.0

    q_set = set(query_terms)
    c_set = set(chunk_terms)
    overlap = len(q_set.intersection(c_set))
    coverage = overlap / len(q_set)

    # Bigram overlap
    q_bigrams = set(zip(query_terms[:-1], query_terms[1:])) if len(query_terms) > 1 else set()
    c_bigrams = set(zip(chunk_terms[:-1], chunk_terms[1:])) if len(chunk_terms) > 1 else set()
    bigram_overlap = len(q_bigrams.intersection(c_bigrams)) if q_bigrams else 0.0
    bigram_score = (bigram_overlap / len(q_bigrams)) if q_bigrams else 0.0

    return (0.6 * coverage) + (0.4 * bigram_score)

def rerank_passages(
    query: str,
    candidates: List[Tuple[TextChunk, float]],
    top_k: int = 5,
    rrf_k: int = 60
) -> List[Tuple[TextChunk, float]]:
    """
    Combines initial BM25 score rank with dense lexical overlap rank
    via Reciprocal Rank Fusion: RRF = 1/(k + rank_bm25) + 1/(k + rank_density).
    """
    if not candidates:
        return []

    q_terms = tokenize(query)

    # Rank 1: Original BM25 ordering
    bm25_ranks = {chunk.chunk_id: rank + 1 for rank, (chunk, _) in enumerate(candidates)}

    # Rank 2: Density ordering
    scored_by_density = []
    for chunk, _ in candidates:
        c_terms = tokenize(chunk.text)
        density = compute_density_score(q_terms, c_terms)
        scored_by_density.append((chunk, density))

    scored_by_density.sort(key=lambda x: x[1], reverse=True)
    density_ranks = {chunk.chunk_id: rank + 1 for rank, (chunk, _) in enumerate(scored_by_density)}

    # Merge via RRF
    chunk_map = {chunk.chunk_id: chunk for chunk, _ in candidates}
    rrf_scores = {}
    for cid, chunk in chunk_map.items():
        r1 = bm25_ranks[cid]
        r2 = density_ranks[cid]
        rrf = (1.0 / (rrf_k + r1)) + (1.0 / (rrf_k + r2))
        rrf_scores[cid] = rrf

    sorted_res = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [(chunk_map[cid], score) for cid, score in sorted_res]
