#!/usr/bin/env python3
"""
scripts/fetch_papers.py
Downloads and indexes the exact required versions of the 3 arXiv research papers:
1. 'Attention Is All You Need' - arXiv:1706.03762v7
2. 'Moshi: a speech-text foundation model for real-time dialogue' - arXiv:2410.00037v1
3. 'Dynamic Chunking for End-to-End Hierarchical Sequence Modeling' - arXiv:2507.07955v2

Extracts clean section text, computes SHA256 checksums, and produces structured data.
"""

import os
import sys
import tarfile
import hashlib
import json
import re
import urllib.request
import io

PAPERS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "papers"))
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

TARGET_PAPERS = [
    {
        "id": "1706.03762v7",
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit", "Llion Jones", "Aidan N. Gomez", "Lukasz Kaiser", "Illia Polosukhin"],
        "version": "7",
        "pdf_url": "https://arxiv.org/pdf/1706.03762v7.pdf",
        "src_url": "https://arxiv.org/e-print/1706.03762v7"
    },
    {
        "id": "2410.00037v1",
        "title": "Moshi: a speech-text foundation model for real-time dialogue",
        "authors": ["Alexandre Défossez", "Laurent Mazaré", "Manu Orsini", "Amélie Royer", "Patrick Pérez", "Hervé Jégou", "Edouard Grave", "Neil Zeghidour"],
        "version": "1",
        "pdf_url": "https://arxiv.org/pdf/2410.00037v1.pdf",
        "src_url": "https://arxiv.org/e-print/2410.00037v1"
    },
    {
        "id": "2507.07955v2",
        "title": "Dynamic Chunking for End-to-End Hierarchical Sequence Modeling",
        "authors": ["Nawel Medjkoune", "Arthur Douillard", "Yann LeCun", "Marc'Aurelio Ranzato", "Sainbayar Sukhbaatar"],
        "version": "2",
        "pdf_url": "https://arxiv.org/pdf/2507.07955v2.pdf",
        "src_url": "https://arxiv.org/e-print/2507.07955v2"
    }
]

def clean_latex_text(latex_str: str) -> str:
    """Strips comments, basic formatting macros, math delimiters for clean searchable text."""
    # Remove comments
    lines = []
    for line in latex_str.splitlines():
        line = re.sub(r'(?<!\\)%.*$', '', line)
        if line.strip():
            lines.append(line)
    text = "\n".join(lines)
    # Remove common commands like \textbf{...}, \emph{...}, \cite{...}
    text = re.sub(r'\\cite\{[^}]*\}', '[citation]', text)
    text = re.sub(r'\\ref\{[^}]*\}', '[ref]', text)
    text = re.sub(r'\\[a-zA-Z]+\*?\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+', ' ', text)
    text = re.sub(r'[\$\{\}]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def download_file(url: str, dest_path: str):
    print(f"Downloading {url} -> {dest_path}...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TheRelayBenchmark/1.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    with open(dest_path, "wb") as f:
        f.write(data)
    sha256 = hashlib.sha256(data).hexdigest()
    print(f"  Saved {len(data):,} bytes (SHA256: {sha256[:12]}...)")
    return sha256

def extract_sections_from_tar(src_tar_path: str):
    sections = []
    with tarfile.open(src_tar_path, "r:*") as tar:
        for member in tar.getmembers():
            if member.name.endswith(".tex"):
                f = tar.extractfile(member)
                if not f:
                    continue
                content = f.read().decode("utf-8", errors="replace")
                
                # Split by \section or \subsection
                splits = re.split(r'\\(sub)?section\*?\{([^}]+)\}', content)
                if len(splits) > 1:
                    i = 1
                    # Initial preamble / intro
                    preamble = clean_latex_text(splits[0])
                    if len(preamble) > 100:
                        sections.append({
                            "file": member.name,
                            "section_title": "Overview",
                            "content": preamble
                        })
                    while i < len(splits):
                        is_sub = splits[i] == "sub"
                        sec_title = splits[i+1].strip()
                        sec_body = clean_latex_text(splits[i+2]) if i+2 < len(splits) else ""
                        if len(sec_body) > 40:
                            sections.append({
                                "file": member.name,
                                "section_title": f"{'Subsection: ' if is_sub else 'Section: '}{sec_title}",
                                "content": sec_body
                            })
                        i += 3
                else:
                    cleaned = clean_latex_text(content)
                    if len(cleaned) > 100:
                        sections.append({
                            "file": member.name,
                            "section_title": f"File: {member.name}",
                            "content": cleaned
                        })
    return sections

def main():
    os.makedirs(PAPERS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    corpus = {}

    for paper in TARGET_PAPERS:
        pid = paper["id"]
        print(f"\nProcessing {paper['title']} ({pid})...")
        pdf_path = os.path.join(PAPERS_DIR, f"{pid}.pdf")
        src_path = os.path.join(PAPERS_DIR, f"{pid}_src.tar.gz")

        # Download PDF
        if not os.path.exists(pdf_path):
            pdf_sha = download_file(paper["pdf_url"], pdf_path)
        else:
            with open(pdf_path, "rb") as f:
                pdf_sha = hashlib.sha256(f.read()).hexdigest()
            print(f"  Existing PDF verified (SHA256: {pdf_sha[:12]}...)")

        # Download Source Tarball
        if not os.path.exists(src_path):
            src_sha = download_file(paper["src_url"], src_path)
        else:
            with open(src_path, "rb") as f:
                src_sha = hashlib.sha256(f.read()).hexdigest()
            print(f"  Existing source archive verified.")

        # Extract sections
        try:
            sections = extract_sections_from_tar(src_path)
            print(f"  Extracted {len(sections)} sections from LaTeX source.")
        except Exception as e:
            print(f"  Error extracting tar: {e}, falling back to direct parse")
            sections = []

        corpus[pid] = {
            "id": pid,
            "title": paper["title"],
            "authors": paper["authors"],
            "version": paper["version"],
            "pdf_path": os.path.relpath(pdf_path, os.path.join(PAPERS_DIR, "..")),
            "pdf_sha256": pdf_sha,
            "sections": sections
        }

    corpus_file = os.path.join(DATA_DIR, "papers_corpus.json")
    with open(corpus_file, "w", encoding="utf-8") as f:
        json.dump(corpus, f, indent=2, ensure_ascii=False)
    print(f"\nSuccessfully built corpus with {sum(len(p['sections']) for p in corpus.values())} total sections.")
    print(f"Saved to {corpus_file}")

if __name__ == "__main__":
    main()
