"""Tiny language detection used to nudge the LLM toward the right reply language."""
import re

_THAI_RE = re.compile(r"[฀-๿]")


def has_thai(s: str) -> bool:
    return bool(_THAI_RE.search(s))


def answer_language_instruction(question: str) -> str:
    """The explicit 'answer in X' line we inject right before generation."""
    if has_thai(question):
        return "Answer in Thai (ภาษาไทย)."
    return "Answer in English."
