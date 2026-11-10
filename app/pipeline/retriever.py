"""
app/pipeline/retriever.py
Stage 2: Tool-Based Retrieval Engine.
Implements the genuine tool call 'retrieve_passages' with adaptive degradation
under token pressure (Engineering Contribution 2).
"""

import os
import json
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional

from app.retrieval.chunking import chunk_paper_sections, TextChunk
from app.retrieval.indexing import BM25Index
from app.retrieval.reranking import rerank_passages
from app.config import CONFIG

@dataclass
class RetrievalResult:
    chunks: List[Tuple[TextChunk, float]]
    setting_used: str
    top_k: int
    reranked: bool
    degraded_under_pressure: bool
    total_context_tokens: int

class RetrieverTool:
    def __init__(self, corpus_path: Optional[str] = None):
        self.corpus_path = corpus_path or CONFIG.corpus_json_path
        self._indices: Dict[str, BM25Index] = {}
        self._chunks_by_setting: Dict[str, List[TextChunk]] = {}
        self._load_and_index()

    def _load_and_index(self):
        if not os.path.exists(self.corpus_path):
            raise FileNotFoundError(f"Corpus file not found: {self.corpus_path}. Run scripts/fetch_papers.py first.")

        with open(self.corpus_path, "r", encoding="utf-8") as f:
            corpus = json.load(f)

        # Build chunks for each setting
        # Setting A: Small chunk (180 words), top 3, no rerank
        chunks_a = chunk_paper_sections(corpus, chunk_size_words=180, overlap_words=25, setting_name="A")
        self._chunks_by_setting["A"] = chunks_a
        self._indices["A"] = BM25Index(chunks_a)

        # Setting B: Medium chunk (360 words), top 5, no rerank
        chunks_b = chunk_paper_sections(corpus, chunk_size_words=360, overlap_words=50, setting_name="B")
        self._chunks_by_setting["B"] = chunks_b
        self._indices["B"] = BM25Index(chunks_b)

        # Setting C: Medium chunk (360 words), top 5, WITH rerank
        self._chunks_by_setting["C"] = chunks_b
        self._indices["C"] = self._indices["B"]

        # Setting D: Dynamic hierarchical chunking, top 4, WITH rerank
        chunks_d = chunk_paper_sections(corpus, setting_name="D")
        self._chunks_by_setting["D"] = chunks_d
        self._indices["D"] = BM25Index(chunks_d)

    def retrieve_passages(
        self,
        query: str,
        setting: str = "B",
        remaining_tpm_ratio: float = 1.0
    ) -> RetrievalResult:
        """
        Tool function called by orchestrator.
        If remaining_tpm_ratio < 0.25, degrades to compact context to conserve tokens.
        """
        effective_setting = setting
        degraded = False

        if remaining_tpm_ratio < 0.25 and setting in ("B", "C", "D"):
            # Degrade to Setting A (compact) to preserve token budget
            effective_setting = "A"
            degraded = True

        index = self._indices.get(effective_setting, self._indices["B"])

        top_k_map = {"A": 3, "B": 5, "C": 5, "D": 4}
        top_k = top_k_map.get(effective_setting, 5)

        # Primary BM25 retrieval
        candidates = index.search(query, top_k=top_k * 2)

        # Rerank if Setting C or D
        if effective_setting in ("C", "D") and candidates:
            final_chunks = rerank_passages(query, candidates, top_k=top_k)
            reranked = True
        else:
            final_chunks = candidates[:top_k]
            reranked = False

        # Token estimate
        total_tokens = sum(len(c.text.split()) for c, _ in final_chunks) * 4 // 3

        return RetrievalResult(
            chunks=final_chunks,
            setting_used=effective_setting,
            top_k=top_k,
            reranked=reranked,
            degraded_under_pressure=degraded,
            total_context_tokens=total_tokens
        )
