"""
app/pipeline/query_analyzer.py
Stage 1: Query Understanding & Routing.
Analyzes user intent, estimates computational/token complexity, and identifies targeted papers.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class QueryPlan:
    raw_query: str
    cleaned_query: str
    detected_intent: str # 'factoid', 'comparative', 'methodological', 'adversarial'
    target_paper_hints: List[str]
    estimated_tokens: int
    complexity_score: float # 1.0 (simple) to 3.0 (complex cross-paper)

class QueryAnalyzer:
    def __init__(self):
        self.paper_keywords = {
            "1706.03762v7": ["transformer", "attention", "vaswani", "bleu", "multi-head", "scaled dot-product", "wmt", "encoder-decoder", "positional encoding"],
            "2410.00037v1": ["moshi", "mimi", "speech", "dialogue", "spoken", "audio", "full-duplex", "kyutai", "inner monologue", "codec"],
            "2507.07955v2": ["dynamic chunking", "chunking", "h-net", "hierarchical", "byte-level", "tokenization-free", "dna", "bpb", "segmentation"]
        }

    def analyze(self, query: str) -> QueryPlan:
        lower_q = query.lower()
        hints = []
        for pid, kw_list in self.paper_keywords.items():
            if any(kw in lower_q for kw in kw_list):
                hints.append(pid)

        # Detect intent
        if any(w in lower_q for w in ["compare", "difference", "versus", "vs", "contrast"]):
            intent = "comparative"
            complexity = 2.5
        elif any(w in lower_q for w in ["why", "how", "explain", "architecture", "mechanism"]):
            intent = "methodological"
            complexity = 2.0
        elif any(w in lower_q for w in ["forget gate", "television", "gpt-4", "lora", "wavlm"]):
            intent = "adversarial"
            complexity = 1.5
        else:
            intent = "factoid"
            complexity = 1.0

        est_prompt_tokens = 450 + int(complexity * 250)

        return QueryPlan(
            raw_query=query,
            cleaned_query=query.strip(),
            detected_intent=intent,
            target_paper_hints=hints,
            estimated_tokens=est_prompt_tokens,
            complexity_score=complexity
        )
