"""
tests/test_standin.py
Unit tests for StandinProvider:
- Latency scaling under load
- Rate limit 429 enforcement
- Daily quota exhaustion
- Incremental streaming
"""

import unittest
import asyncio
from app.providers.standin_provider import StandinProvider
from app.config import ProviderLimits, StandinConfig

class TestStandinProvider(unittest.TestCase):
    def test_standin_streaming_and_ttft(self):
        provider = StandinProvider()
        messages = [{"role": "user", "content": "What is Moshi?"}]

        async def run():
            chunks = []
            async for chunk in provider.stream_chat(messages, max_tokens=10):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(run())
        self.assertGreater(len(chunks), 1)
        final_chunk = chunks[-1]
        self.assertTrue(final_chunk.is_final)
        self.assertEqual(final_chunk.status, "ok")
        self.assertIsNotNone(final_chunk.first_token_ms)
        self.assertGreater(final_chunk.total_ms, final_chunk.first_token_ms)

    def test_standin_rate_limit_429(self):
        # Strict provider with limit of 2 requests per minute
        strict_limits = ProviderLimits(rpm=2, tpm=1000)
        provider = StandinProvider(limits=strict_limits)
        messages = [{"role": "user", "content": "Hello"}]

        async def run():
            res = []
            for _ in range(3):
                last_chunk = None
                async for c in provider.stream_chat(messages, max_tokens=5):
                    last_chunk = c
                res.append(last_chunk)
            return res

        results = asyncio.run(run())
        # First 2 succeed
        self.assertEqual(results[0].status, "ok")
        self.assertEqual(results[1].status, "ok")
        # 3rd is rate limited
        self.assertEqual(results[2].status, "rate_limited")
        self.assertIn("429", results[2].error_message)

    def test_standin_daily_budget_exhausted(self):
        provider = StandinProvider()
        provider.daily_budget_exhausted = True
        messages = [{"role": "user", "content": "Hello"}]

        async def run():
            last_chunk = None
            async for c in provider.stream_chat(messages):
                last_chunk = c
            return last_chunk

        res = asyncio.run(run())
        self.assertEqual(res.status, "rate_limited")
        self.assertIn("Daily", res.error_message)

if __name__ == "__main__":
    unittest.main()
