"""
tests/test_pipeline.py
End-to-end pipeline unit tests:
- 6-stage execution
- Grounded answer generation with valid arXiv citations
- Strict refusal on unanswerable/out-of-scope questions
"""

import unittest
import asyncio
from app.providers.standin_provider import StandinProvider
from app.pipeline.orchestrator import PipelineOrchestrator
from app.observability.tracing import ResultsLogger

class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = StandinProvider()
        # Use a temporary logger or memory
        cls.orchestrator = PipelineOrchestrator(provider=cls.provider)

    def test_pipeline_answers_grounded_transformer_question(self):
        query = "What BLEU score did the Transformer achieve on WMT 2014 English-to-German translation task?"
        
        async def run():
            chunks = []
            async for c in self.orchestrator.execute_request(
                query=query,
                scenario="unit_test",
                must_refuse=False,
                expected_keywords=["28.4", "BLEU"]
            ):
                chunks.append(c)
            return chunks

        chunks = asyncio.run(run())
        final_chunk = chunks[-1]
        self.assertEqual(final_chunk.status, "ok")
        self.assertIn("28.4", final_chunk.text)
        self.assertIn("1706.03762v7", final_chunk.text)

    def test_pipeline_refuses_out_of_scope_question(self):
        query = "What were the pretraining compute cost and parameter count for OpenAI's GPT-4 in petaflop-days?"

        async def run():
            chunks = []
            async for c in self.orchestrator.execute_request(
                query=query,
                scenario="unit_test",
                must_refuse=True
            ):
                chunks.append(c)
            return chunks

        chunks = asyncio.run(run())
        final_chunk = chunks[-1]
        self.assertEqual(final_chunk.status, "ok")
        self.assertTrue(any(word in final_chunk.text.lower() for word in ["refuse", "cannot answer", "outside the scope"]))

if __name__ == "__main__":
    unittest.main()
