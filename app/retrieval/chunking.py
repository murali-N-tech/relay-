"""
app/retrieval/chunking.py
Multi-strategy chunking implementations corresponding to experimental settings:
- Setting A: Small chunk (~180 words / ~240 tokens), overlap 25
- Setting B: Medium chunk (~360 words / ~480 tokens), overlap 50
- Setting C: Medium chunk with re-ranking
- Setting D: Dynamic hierarchical chunking (Section-aligned natural boundaries)
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class TextChunk:
    chunk_id: str
    paper_id: str
    paper_title: str
    section_title: str
    text: str
    word_count: int
    char_count: int
    setting: str

def clean_tokens(text: str) -> List[str]:
    return [w for w in re.split(r'\s+', text.strip()) if w]

def chunk_paper_sections(
    corpus: Dict[str, Any],
    chunk_size_words: int = 350,
    overlap_words: int = 40,
    setting_name: str = "B"
) -> List[TextChunk]:
    chunks = []
    chunk_counter = 0

    for pid, paper_data in corpus.items():
        title = paper_data["title"]
        sections = paper_data.get("sections", [])

        for sec in sections:
            sec_title = sec.get("section_title", "Section")
            content = sec.get("content", "")
            words = clean_tokens(content)

            if not words:
                continue

            if setting_name == "D":
                # Dynamic hierarchical: preserve full section if reasonable, else split on paragraphs
                paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 30]
                if not paragraphs:
                    paragraphs = [content]
                
                curr_para_words = []
                for p in paragraphs:
                    p_words = clean_tokens(p)
                    if len(curr_para_words) + len(p_words) > 400 and curr_para_words:
                        chunk_counter += 1
                        chunk_text = " ".join(curr_para_words)
                        chunks.append(TextChunk(
                            chunk_id=f"chk_{chunk_counter:04d}",
                            paper_id=pid,
                            paper_title=title,
                            section_title=sec_title,
                            text=chunk_text,
                            word_count=len(curr_para_words),
                            char_count=len(chunk_text),
                            setting=setting_name
                        ))
                        curr_para_words = p_words
                    else:
                        curr_para_words.extend(p_words)

                if curr_para_words:
                    chunk_counter += 1
                    chunk_text = " ".join(curr_para_words)
                    chunks.append(TextChunk(
                        chunk_id=f"chk_{chunk_counter:04d}",
                        paper_id=pid,
                        paper_title=title,
                        section_title=sec_title,
                        text=chunk_text,
                        word_count=len(curr_para_words),
                        char_count=len(chunk_text),
                        setting=setting_name
                    ))
            else:
                # Fixed sliding window
                step = max(1, chunk_size_words - overlap_words)
                for start_idx in range(0, len(words), step):
                    window = words[start_idx : start_idx + chunk_size_words]
                    if len(window) < 30 and chunks: # Avoid tiny tail chunks
                        break
                    chunk_counter += 1
                    chunk_text = " ".join(window)
                    chunks.append(TextChunk(
                        chunk_id=f"chk_{chunk_counter:04d}",
                        paper_id=pid,
                        paper_title=title,
                        section_title=sec_title,
                        text=chunk_text,
                        word_count=len(window),
                        char_count=len(chunk_text),
                        setting=setting_name
                    ))

    return chunks
