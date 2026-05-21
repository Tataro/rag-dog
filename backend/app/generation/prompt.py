"""Build the RAG generation prompt and parse citation markers out of the answer."""
import re

from ..lang import answer_language_instruction
from ..retrieval.search import Hit

SYSTEM = (
    "You are a helpful assistant answering the user's CURRENT question, "
    "using ONLY the context passages provided in the latest user message. "
    "Focus tightly on what the current question asks — do NOT repeat or pivot "
    "to topics from earlier in the conversation. Prior turns are background only. "
    "If the answer to the current question is not in the context, say you don't know — "
    "do not fall back to an earlier answer. "
    "When you use information from a passage, mark the source inline with its bracket "
    "number, e.g. [1] or [2]. You may cite multiple passages. "
    "Match the language of the user's current question exactly: "
    "Thai question → Thai answer; English question → English answer. "
    "Ignore the language of the conversation history and the context passages "
    "when deciding the reply language."
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
    # The language instruction goes LAST — recency bias makes the model most
    # likely to obey the directive sitting right before it generates.
    return (
        "Context passages:\n\n"
        f"{build_context_block(hits)}\n\n"
        "---\n"
        f"Question: {question}\n\n"
        f"{answer_language_instruction(question)} "
        "Cite sources inline using [n].\n\n"
        "Answer:"
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
