"""
app/retrieval/indexing.py
High-performance BM25Okapi inverted index with term frequency, document length normalization,
and exact section provenance tracking.
"""

import math
import re
from typing import List, Dict, Any, Tuple
from collections import defaultdict, Counter

from app.retrieval.chunking import TextChunk

def tokenize(text: str) -> List[str]:
    """Lowercases, strips punctuation, and tokens into terms."""
    return re.findall(r'[a-zA-Z0-9_\-\.]+', text.lower())

class BM25Index:
    def __init__(self, chunks: List[TextChunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.doc_count = len(chunks)
        self.doc_lengths = []
        self.inverted_index: Dict[str, List[Tuple[int, int]]] = defaultdict(list) # term -> [(doc_idx, freq)]
        self.df: Dict[str, int] = defaultdict(int) # term -> doc freq
        self.idf: Dict[str, float] = {}
        self.avg_doc_len = 0.0

        self._build_index()

    def _build_index(self):
        total_len = 0
        for doc_idx, chunk in enumerate(self.chunks):
            # Combine title, section, and text for rich indexing
            full_text = f"{chunk.paper_title} {chunk.section_title} {chunk.text}"
            terms = tokenize(full_text)
            doc_len = len(terms)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            term_counts = Counter(terms)
            for term, count in term_counts.items():
                self.inverted_index[term].append((doc_idx, count))
                self.df[term] += 1

        self.avg_doc_len = (total_len / self.doc_count) if self.doc_count > 0 else 1.0

        # Precompute IDF using standard BM25 formula
        for term, freq in self.df.items():
            idf_val = math.log(1.0 + (self.doc_count - freq + 0.5) / (freq + 0.5))
            self.idf[term] = max(0.01, idf_val)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[TextChunk, float]]:
        """Scores all matching documents against the query terms using BM25Okapi."""
        query_terms = tokenize(query)
        scores: Dict[int, float] = defaultdict(float)

        for term in query_terms:
            if term not in self.inverted_index:
                continue
            idf_term = self.idf[term]
            postings = self.inverted_index[term]

            for doc_idx, tf in postings:
                doc_len = self.doc_lengths[doc_idx]
                norm = 1.0 - self.b + self.b * (doc_len / self.avg_doc_len)
                num = tf * (self.k1 + 1.0)
                den = tf + self.k1 * norm
                scores[doc_idx] += idf_term * (num / den)

        if not scores:
            return []

        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [(self.chunks[doc_idx], score) for doc_idx, score in sorted_docs]
