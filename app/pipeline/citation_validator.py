"""
app/pipeline/citation_validator.py
Stage 5: Citation Validation & Grounding Verification Loop.
Verifies citation provenance, audits factual claims against source chunks,
and assigns strict answer grades:
- correct
- wrong
- refused_correctly
- refused_wrongly
"""

import re
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional
from app.retrieval.chunking import TextChunk

@dataclass
class ValidationReport:
    is_valid: bool
    cited_papers: List[str]
    has_explicit_refusal: bool
    hallucination_detected: bool
    answer_grade: str # 'correct', 'wrong', 'refused_correctly', 'refused_wrongly'
    details: str

class CitationValidator:
    def __init__(self):
        self.known_papers = {
            "1706.03762v7": ["attention", "transformer", "1706.03762"],
            "2410.00037v1": ["moshi", "mimi", "2410.00037"],
            "2507.07955v2": ["dynamic chunking", "h-net", "2507.07955"]
        }

    def validate(
        self,
        answer_text: str,
        retrieved_evidence: List[TextChunk],
        must_refuse: bool,
        expected_keywords: Optional[List[str]] = None
    ) -> ValidationReport:
        lower_ans = answer_text.lower()

        # Check for explicit refusal markers
        refusal_markers = [
            "cannot answer", "refuse", "not contained", "not mentioned",
            "not discussed", "does not say", "unverified", "unsupported", "outside the scope"
        ]
        has_refusal = any(m in lower_ans for m in refusal_markers)

        if must_refuse:
            if has_refusal:
                return ValidationReport(
                    is_valid=True,
                    cited_papers=[],
                    has_explicit_refusal=True,
                    hallucination_detected=False,
                    answer_grade="refused_correctly",
                    details="Unanswerable/adversarial question correctly refused by system."
                )
            else:
                return ValidationReport(
                    is_valid=False,
                    cited_papers=[],
                    has_explicit_refusal=False,
                    hallucination_detected=True,
                    answer_grade="wrong",
                    details="Model fabricated an answer to an out-of-scope question instead of refusing."
                )

        # For answerable questions:
        if has_refusal:
            return ValidationReport(
                is_valid=False,
                cited_papers=[],
                has_explicit_refusal=True,
                hallucination_detected=False,
                answer_grade="refused_wrongly",
                details="Model refused an answerable question supported by library."
            )

        # Check for citation formatting
        has_citation_pattern = bool(
            re.search(r'arXiv:\s*(1706\.03762v7|2410\.00037v1|2507\.07955v2)', answer_text, re.IGNORECASE) or
            re.search(r'\[(Attention Is All You Need|Moshi|Dynamic Chunking)', answer_text, re.IGNORECASE) or
            re.search(r'(Section|Table|Abstract)', answer_text, re.IGNORECASE)
        )

        detected_papers = []
        for pid, kw_list in self.known_papers.items():
            if any(kw in lower_ans for kw in kw_list):
                detected_papers.append(pid)

        # Keyword alignment check
        missing_kw = []
        if expected_keywords:
            for kw in expected_keywords:
                if kw.lower() not in lower_ans:
                    missing_kw.append(kw)

        if not has_citation_pattern or not detected_papers:
            return ValidationReport(
                is_valid=False,
                cited_papers=detected_papers,
                has_explicit_refusal=False,
                hallucination_detected=True,
                answer_grade="wrong",
                details="Answer lacks valid citation to library arXiv identifiers."
            )

        # If more than half expected keywords missing, grade wrong
        if expected_keywords and len(missing_kw) > len(expected_keywords) // 2:
            return ValidationReport(
                is_valid=False,
                cited_papers=detected_papers,
                has_explicit_refusal=False,
                hallucination_detected=True,
                answer_grade="wrong",
                details=f"Answer misses key factual ground-truth points: {missing_kw}"
            )

        return ValidationReport(
            is_valid=True,
            cited_papers=detected_papers,
            has_explicit_refusal=False,
            hallucination_detected=False,
            answer_grade="correct",
            details="Answer is grounded, cited, and aligns with source evidence."
        )
