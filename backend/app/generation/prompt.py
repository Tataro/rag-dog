"""Build the RAG generation prompt and parse citation markers out of the answer."""
import re

from ..retrieval.search import Hit

SYSTEM = (
    "You are a helpful assistant that answers ONLY using the context passages provided. "
    "If the answer is not in the context, say you don't know. "
    "When you use information from a passage, mark the source inline with its bracket "
    "number, e.g. [1] or [2]. You may cite multiple passages. "
    "Answer in the same language as the user's question."
)


def build_context_block(hits: list[Hit]) -> str:
    lines: list[str] = []
    for i, hit in enumerate(hits, start=1):
        header = hit.filename
        if hit.page is not None:
            header += f", p.{hit.page}"
        if hit.section:
            header += f", § {hit.section}"
        lines.append(f"[{i}] {header}\n{hit.text}")
    return "\n\n".join(lines)


def build_user_prompt(question: str, hits: list[Hit]) -> str:
    return (
        "Context passages:\n\n"
        f"{build_context_block(hits)}\n\n"
        "---\n"
        f"Question: {question}\n\n"
        "Answer (cite sources inline using [n]):"
    )


_MARKER_RE = re.compile(r"\[(\d+)\]")


def cited_markers(answer: str) -> list[int]:
    """Return distinct citation markers in order of first appearance."""
    seen: list[int] = []
    for m in _MARKER_RE.finditer(answer):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen
