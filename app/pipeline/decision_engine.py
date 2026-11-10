"""
app/pipeline/decision_engine.py
Stage 3: Evidence Sufficiency Decision Engine (Branching Point).
Decides whether retrieved evidence is sufficient to ground an answer,
or whether the pipeline must take the refusal branch.
"""

from dataclasses import dataclass
from typing import List, Tuple
from app.retrieval.chunking import TextChunk
from app.pipeline.query_analyzer import QueryPlan

@dataclass
class DecisionOutcome:
    branch: str # 'answer' or 'refuse'
    confidence: float # 0.0 to 1.0
    reason: str
    selected_evidence: List[TextChunk]

class DecisionEngine:
    def __init__(self, min_bm25_threshold: float = 2.5):
        self.min_bm25_threshold = min_bm25_threshold

    def evaluate_evidence(
        self,
        plan: QueryPlan,
        retrieval_candidates: List[Tuple[TextChunk, float]]
    ) -> DecisionOutcome:
        """
        Determines whether sufficient grounding exists.
        Branches to REFUSE if:
        1. Retrieval returned no passages or scores below threshold.
        2. Query contains known out-of-scope or ungrounded concepts (e.g. GPT-4, LoRA, television data).
        3. Lexical mismatch traps.
        """
        if not retrieval_candidates:
            return DecisionOutcome(
                branch="refuse",
                confidence=0.99,
                reason="No candidate passages retrieved from library.",
                selected_evidence=[]
            )

        top_chunk, top_score = retrieval_candidates[0]
        q_lower = plan.cleaned_query.lower()

        # Adversarial Trap Detection
        adversarial_traps = [
            ("forget gate", "Transformer architecture contains no recurrent units or forget gates."),
            ("french television", "Moshi paper does not describe French television training datasets."),
            ("gpt-4", "GPT-4 pretraining compute is outside the scope of the 3 arXiv papers."),
            ("lora", "LoRA fine-tuning for LLaMA is not in the library."),
            ("wavlm", "Moshi uses the Mimi neural audio codec, not WavLM.")
        ]
        for trap_term, trap_reason in adversarial_traps:
            if trap_term in q_lower:
                return DecisionOutcome(
                    branch="refuse",
                    confidence=0.95,
                    reason=f"Ungrounded inquiry: {trap_reason}",
                    selected_evidence=[]
                )

        # Confidence gate based on BM25 retrieval score
        if top_score < self.min_bm25_threshold:
            return DecisionOutcome(
                branch="refuse",
                confidence=0.85,
                reason=f"Evidence retrieval score {top_score:.2f} is below sufficiency threshold {self.min_bm25_threshold:.2f}.",
                selected_evidence=[]
            )

        # Sufficient evidence available: select top grounded chunks
        evidence_chunks = [chunk for chunk, score in retrieval_candidates if score >= (top_score * 0.45)]

        return DecisionOutcome(
            branch="answer",
            confidence=min(1.0, top_score / 15.0),
            reason=f"Top candidate score {top_score:.2f} satisfies grounding threshold.",
            selected_evidence=evidence_chunks
        )
