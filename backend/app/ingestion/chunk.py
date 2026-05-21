"""Split parsed blocks into ~1000-token chunks with ~100-token overlap.

Chunks never cross block boundaries — pages and sections stay intact at chunk edges,
which means a chunk's `page` and `section` are unambiguous.

Token count uses tiktoken's cl100k_base encoding. It's not the model's true tokenizer,
but it's close enough to size chunks predictably across English and Thai.
"""
from dataclasses import dataclass

import tiktoken

from ..config import settings
from .parse import Block

_ENC = tiktoken.get_encoding("cl100k_base")


@dataclass(slots=True)
class Chunk:
    text: str
    page: int | None
    section: str | None
    token_count: int


def chunk_blocks(blocks: list[Block]) -> list[Chunk]:
    size = settings.chunk_size_tokens
    overlap = settings.chunk_overlap_tokens
    chunks: list[Chunk] = []

    for block in blocks:
        tokens = _ENC.encode(block.text)
        if not tokens:
            continue

        if len(tokens) <= size:
            chunks.append(Chunk(text=block.text, page=block.page, section=block.section, token_count=len(tokens)))
            continue

        start = 0
        while start < len(tokens):
            end = min(start + size, len(tokens))
            window = tokens[start:end]
            text = _ENC.decode(window)
            chunks.append(Chunk(text=text, page=block.page, section=block.section, token_count=len(window)))
            if end == len(tokens):
                break
            start = end - overlap

    return chunks
