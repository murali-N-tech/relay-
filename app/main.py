"""
app/main.py
CLI and API entry point for The Relay AI Inference System.
Supports interactive query answering, direct benchmark execution,
and lightweight HTTP serving for the frontend dashboard.
"""

import sys
import os
import json
import asyncio
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

from app.config import CONFIG
from app.providers.standin_provider import StandinProvider
from app.providers.groq_provider import GroqProvider
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.retriever import RetrieverTool

async def handle_single_query(query: str, setting: str = "B", provider_type: str = "stand-in"):
    provider = GroqProvider() if provider_type == "real" and CONFIG.groq_api_key else StandinProvider()
    orchestrator = PipelineOrchestrator(provider=provider)

    print(f"\n[QUERY] {query}")
    print(f"[SETTING] {setting} | [PROVIDER] {provider.name}")
    print("-" * 60)

    full_response = []
    first_token_reported = False

    async for chunk in orchestrator.execute_request(query, retrieval_setting=setting):
        if not chunk.is_final and chunk.text:
            if not first_token_reported and chunk.first_token_ms:
                print(f"[TTFT: {chunk.first_token_ms:.1f}ms] ", end="", flush=True)
                first_token_reported = True
            print(chunk.text, end="", flush=True)
            full_response.append(chunk.text)
        elif chunk.is_final:
            print("\n" + "-" * 60)
            print(f"[STATUS] {chunk.status}")
            print(f"[TTFT] {chunk.first_token_ms or 0:.1f} ms | [TOTAL] {chunk.total_ms:.1f} ms")
            print(f"[TOKENS IN/OUT] {chunk.tokens_in} / {chunk.tokens_out}")
            if chunk.error_message:
                print(f"[ERROR] {chunk.error_message}")

def run_server(port: int = 8000):
    """Simple API server bridging to Python pipeline."""
    retriever = RetrieverTool()
    provider = StandinProvider()
    orchestrator = PipelineOrchestrator(provider=provider, retriever=retriever)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                status_data = {
                    "provider": provider.name,
                    "limits": {
                        "rpm": provider.limits.rpm,
                        "tpm": provider.limits.tpm,
                        "rpd": provider.limits.rpd
                    },
                    "corpus_loaded": True
                }
                self.wfile.write(json.dumps(status_data).encode("utf-8"))
            elif parsed.path == "/api/summary":
                summary_file = os.path.join(os.path.dirname(__file__), "..", "results", "experiment_summary.json")
                if os.path.exists(summary_file):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    with open(summary_file, "rb") as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/query":
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len).decode("utf-8")
                req_data = json.loads(body)
                q = req_data.get("query", "")
                setting = req_data.get("setting", "B")

                async def execute():
                    last_c = None
                    chunks = []
                    async for c in orchestrator.execute_request(q, retrieval_setting=setting):
                        if not c.is_final and c.text:
                            chunks.append(c.text)
                        elif c.is_final:
                            last_c = c
                    return chunks, last_c

                chunks, last_c = asyncio.run(execute())

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                res_obj = {
                    "text": last_c.text if last_c else "".join(chunks),
                    "status": last_c.status if last_c else "error",
                    "first_token_ms": last_c.first_token_ms if last_c else None,
                    "total_ms": last_c.total_ms if last_c else 0.0,
                    "tokens_in": last_c.tokens_in if last_c else 0,
                    "tokens_out": last_c.tokens_out if last_c else 0
                }
                self.wfile.write(json.dumps(res_obj).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Starting pipeline API server on port {port}...")
    server.serve_forever()

def main():
    parser = argparse.ArgumentParser(description="The Relay AI Inference System")
    parser.add_argument("--query", type=str, help="Question to ask the research paper library")
    parser.add_argument("--setting", type=str, default="B", choices=["A", "B", "C", "D"], help="Retrieval setting")
    parser.add_argument("--provider", type=str, default="stand-in", choices=["stand-in", "real"], help="Provider type")
    parser.add_argument("--server", action="store_true", help="Run local HTTP API bridge")
    parser.add_argument("--port", type=int, default=8000, help="Server port")

    args = parser.parse_args()

    if args.server:
        run_server(args.port)
    elif args.query:
        asyncio.run(handle_single_query(args.query, args.setting, args.provider))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
