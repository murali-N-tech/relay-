"""
app/pipeline/answer_generator.py
Stage 4: Answer Drafting & Academic Prompt Engineering.
Builds strictly grounded system and user messages requiring explicit arXiv citations.
"""

from typing import List, Dict
from app.retrieval.chunking import TextChunk

class AnswerGenerator:
    def build_refusal_response(self, reason: str) -> str:
        return (
            f"I cannot answer this question based on the provided three arXiv papers. "
            f"Reason: {reason}. "
            f"Under strict grounding constraints, I refuse to speculate or provide unverified claims."
        )

    def build_prompt_messages(self, query: str, evidence: List[TextChunk]) -> List[Dict[str, str]]:
        context_blocks = []
        for i, chunk in enumerate(evidence):
            block = (
                f"[Document {i+1}]\n"
                f"Paper: {chunk.paper_title} (arXiv:{chunk.paper_id})\n"
                f"Section: {chunk.section_title}\n"
                f"Passage:\n{chunk.text}\n"
            )
            context_blocks.append(block)

        context_str = "\n".join(context_blocks)

        system_msg = (
            "You are a strict, production-grade technical research assistant. "
            "You answer questions EXCLUSIVELY using the provided research paper passages below. "
            "REQUIREMENTS:\n"
            "1. Every factual claim MUST cite the source paper title, arXiv identifier (including version), "
            "and section name (e.g. '[Attention Is All You Need, arXiv:1706.03762v7, Section 3.2]').\n"
            "2. If the passages do not explicitly state the answer, state clearly that the library does not contain this information.\n"
            "3. Do not invent formulas, figures, or hyperparameters not present in the excerpts.\n"
            "4. Be concise, mathematically precise, and technically rigorous."
        )

        user_msg = (
            f"Retrieved Passages from Paper Library:\n\n{context_str}\n\n"
            f"Question: {query}\n\n"
            f"Provide your cited, grounded answer:"
        )

        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ]
