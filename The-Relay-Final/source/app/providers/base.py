"""
app/providers/base.py
Abstract base class and data structures for model inference providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, List, Dict, Any, Optional

@dataclass
class StreamChunk:
    text: str
    first_token_ms: Optional[float] = None
    total_ms: Optional[float] = None
    tokens_in: int = 0
    tokens_out: int = 0
    status: str = "ok" # "ok", "rate_limited", "timeout", "error"
    error_message: Optional[str] = None
    is_final: bool = False
    rate_limit_headers: Dict[str, str] = field(default_factory=dict)

class InferenceProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name: 'real' or 'stand-in'"""
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.0,
        deadline_ms: Optional[float] = None,
        request_id: str = ""
    ) -> AsyncIterator[StreamChunk]:
        """Yields incremental StreamChunk objects with nanosecond timing."""
        pass
