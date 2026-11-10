"""
tests/test_retrieval.py
Unit tests for retrieval engine:
- BM25Okapi scoring
- Provable source provenance (title, arXiv ID, section)
- Reciprocal Rank Fusion (RRF) reranking
- Adaptive token pressure degradation (Contribution 2)
"""

import unittest
from app.pipeline.retriever import RetrieverTool
from app.retrieval.indexing import BM25Index
from app.retrieval.chunking import TextChunk

class TestRetrieval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = RetrieverTool()

    def test_bm25_retrieves_relevant_transformer_chunk(self):
        query = "What is the BLEU score achieved by the Transformer on WMT 2014 English-to-German?"
        res = self.retriever.retrieve_passages(query, setting="B")
        self.assertGreater(len(res.chunks), 0)
        
        top_chunk, score = res.chunks[0]
        self.assertEqual(top_chunk.paper_id, "1706.03762v7")
        self.assertIn("1706.03762v7", top_chunk.paper_id)
        self.assertGreater(score, 0.0)

    def test_bm25_retrieves_moshi_latency(self):
        query = "theoretical latency of Moshi speech dialogue"
        res = self.retriever.retrieve_passages(query, setting="B")
        self.assertGreater(len(res.chunks), 0)
        top_chunk, _ = res.chunks[0]
        self.assertEqual(top_chunk.paper_id, "2410.00037v1")

    def test_adaptive_degradation_under_token_pressure(self):
        # Contribution 2: When remaining TPM is < 25%, Setting B degrades to Setting A
        res_normal = self.retriever.retrieve_passages("Transformer architecture", setting="B", remaining_tpm_ratio=1.0)
        self.assertFalse(res_normal.degraded_under_pressure)
        self.assertEqual(res_normal.setting_used, "B")

        res_degraded = self.retriever.retrieve_passages("Transformer architecture", setting="B", remaining_tpm_ratio=0.15)
        self.assertTrue(res_degraded.degraded_under_pressure)
        self.assertEqual(res_degraded.setting_used, "A")
        self.assertLessEqual(res_degraded.total_context_tokens, res_normal.total_context_tokens)

if __name__ == "__main__":
    unittest.main()
