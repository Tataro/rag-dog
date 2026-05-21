"""Turn a follow-up question into a standalone retrieval query using prior turns."""
import re

from ..generation.llm import chat
from ..lang import has_thai

_SYSTEM = (
    "You rewrite a user's latest message into a standalone search query "
    "that includes any context required from the conversation history. "
    "Output ONLY the rewritten query, no preamble, no quotes, no explanation. "
    "Do NOT include citation markers like [1], [2] — those are artifacts of "
    "the assistant's prior answers and are noise for retrieval. "
    "CRITICAL: write the rewritten query in the SAME language and script as "
    "the latest user message. If the user wrote Thai, output Thai. If English, "
    "output English. Never translate."
)

# Matches bracket citation markers like [1], [12], including chained ones [2][5].
_MARKER_RE = re.compile(r"\s*\[\d+\]")


async def rewrite(history: list[dict], latest_user_text: str) -> str:
    if not history:
        return latest_user_text

    # Strip citation markers from the assistant's prior turns before feeding them
    # back in — otherwise the model is much more likely to mimic them.
    sanitized = [
        {"role": m["role"], "content": _MARKER_RE.sub("", m["content"])} for m in history[-10:]
    ]
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in sanitized)
    # Be symmetric and explicit. Saying "the same language as the latest message"
    # is too indirect — the model drifts to whichever language dominates the
    # transcript (usually Thai, since the docs are Thai).
    target_lang = "Thai (ภาษาไทย)" if has_thai(latest_user_text) else "English"
    user_prompt = (
        f"Conversation so far:\n{transcript}\n\n"
        f"Latest user message: {latest_user_text}\n\n"
        f"Rewrite the latest user message into a standalone retrieval query. "
        f"Write the query in {target_lang}. Do not translate. Output the query only.\n\n"
        "Rewritten query:"
    )
    out = await chat(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
    )
    # Defensive: strip quoting and any citation markers the model leaked anyway.
    cleaned = _MARKER_RE.sub("", out).strip().strip('"').strip("'")
    return cleaned or latest_user_text
