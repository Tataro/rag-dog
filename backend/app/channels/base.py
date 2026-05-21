"""Shared helpers for channel adapters (Telegram, Line)."""
from ..generation.pipeline import QueryResult
from ..schemas import Citation


def format_citations_footer(citations: list[Citation]) -> str:
    if not citations:
        return ""
    parts: list[str] = []
    for c in citations:
        loc = c.filename
        if c.page is not None:
            loc += f" (p.{c.page})"
        elif c.section:
            loc += f" (§ {c.section})"
        parts.append(f"{c.marker}. {loc}")
    return "\n\n📎 " + " · ".join(parts)


def format_bot_reply(result: QueryResult) -> str:
    return result.answer + format_citations_footer(result.citations)
