"""
app/providers/groq_provider.py
Real hosted Groq API provider client with streaming SSE, precise nanosecond latency instrumentation,
and HTTP rate-limit header parsing.
"""

import time
import json
import asyncio
from typing import AsyncIterator, List, Dict, Any, Optional
import urllib.request
import urllib.error

from app.providers.base import InferenceProvider, StreamChunk
from app.config import CONFIG

class GroqProvider(InferenceProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or CONFIG.groq_api_key
        self.model = model or CONFIG.groq_model
        self.base_url = CONFIG.groq_base_url
        self._last_rate_limit_headers: Dict[str, str] = {}

    @property
    def name(self) -> str:
        return "real"

    @property
    def last_rate_limit_headers(self) -> Dict[str, str]:
        return self._last_rate_limit_headers

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.0,
        deadline_ms: Optional[float] = None,
        request_id: str = ""
    ) -> AsyncIterator[StreamChunk]:
        """
        Connects to Groq OpenAI-compatible endpoint, parses SSE chunks,
        and computes time-to-first-token (TTFT) and total latency.
        """
        start_time = time.perf_counter()
        first_token_time: Optional[float] = None
        prompt_tokens_est = sum(len(m["content"]) // 4 for m in messages)
        completion_tokens = 0
        full_text = []

        if not self.api_key:
            yield StreamChunk(
                text="",
                first_token_ms=None,
                total_ms=0.0,
                tokens_in=prompt_tokens_est,
                tokens_out=0,
                status="error",
                error_message="GROQ_API_KEY is not set in environment.",
                is_final=True
            )
            return

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "TheRelay-Benchmark/1.0"
        }

        url = f"{self.base_url}/chat/completions"
        req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")

        # Run connection and streaming in an async executor
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def sync_worker():
            try:
                with urllib.request.urlopen(req, timeout=CONFIG.limits.request_timeout_s) as response:
                    # Capture rate-limit headers
                    headers_dict = {}
                    for k, v in response.headers.items():
                        if "ratelimit" in k.lower() or "retry-after" in k.lower():
                            headers_dict[k.lower()] = v
                    loop.call_soon_threadsafe(queue.put_nowait, ("headers", headers_dict))

                    buffer = ""
                    for raw_line in response:
                        line = raw_line.decode("utf-8", errors="replace")
                        buffer += line
                        while "\n" in buffer:
                            chunk_line, buffer = buffer.split("\n", 1)
                            chunk_line = chunk_line.strip()
                            if chunk_line.startswith("data: "):
                                data_str = chunk_line[6:].strip()
                                if data_str == "[DONE]":
                                    loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
                                    return
                                try:
                                    data_json = json.loads(data_str)
                                    choices = data_json.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            loop.call_soon_threadsafe(queue.put_nowait, ("token", content))
                                except Exception:
                                    pass
                    loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

            except urllib.error.HTTPError as e:
                resp_body = e.read().decode("utf-8", errors="replace")
                headers_dict = {k.lower(): v for k, v in e.headers.items() if "ratelimit" in k.lower() or "retry-after" in k.lower()}
                status_code = e.code
                loop.call_soon_threadsafe(queue.put_nowait, ("http_error", (status_code, resp_body, headers_dict)))
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, ("exc", str(e)))

        worker_future = loop.run_in_executor(None, sync_worker)

        headers_captured = {}
        status = "ok"
        err_msg = None

        while True:
            # Check deadline if set
            if deadline_ms is not None:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                if elapsed_ms > deadline_ms:
                    status = "timeout"
                    err_msg = f"Client SLA deadline exceeded ({elapsed_ms:.1f}ms > {deadline_ms:.1f}ms)"
                    break

            try:
                event_type, event_val = await asyncio.wait_for(queue.get(), timeout=CONFIG.limits.request_timeout_s)
            except asyncio.TimeoutError:
                status = "timeout"
                err_msg = "Socket read timeout waiting for provider chunk"
                break

            if event_type == "headers":
                headers_captured = event_val
                self._last_rate_limit_headers = headers_captured
            elif event_type == "token":
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                completion_tokens += 1
                full_text.append(event_val)
                ttft_ms = (first_token_time - start_time) * 1000.0
                yield StreamChunk(
                    text=event_val,
                    first_token_ms=round(ttft_ms, 2),
                    tokens_in=prompt_tokens_est,
                    tokens_out=completion_tokens,
                    status="ok"
                )
            elif event_type == "done":
                break
            elif event_type == "http_error":
                status_code, body_text, headers_dict = event_val
                self._last_rate_limit_headers = headers_dict
                if status_code == 429:
                    status = "rate_limited"
                else:
                    status = "error"
                err_msg = f"HTTP {status_code}: {body_text}"
                break
            elif event_type == "exc":
                status = "error"
                err_msg = f"Network exception: {event_val}"
                break

        total_ms = (time.perf_counter() - start_time) * 1000.0
        ttft_final = (first_token_time - start_time) * 1000.0 if first_token_time else None

        yield StreamChunk(
            text="".join(full_text),
            first_token_ms=round(ttft_final, 2) if ttft_final else None,
            total_ms=round(total_ms, 2),
            tokens_in=prompt_tokens_est,
            tokens_out=completion_tokens,
            status=status,
            error_message=err_msg,
            is_final=True,
            rate_limit_headers=headers_captured
        )
