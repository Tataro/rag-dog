"""Turn a follow-up question into a standalone retrieval query using prior turns."""
from ..generation.llm import chat

_SYSTEM = (
    "You rewrite a user's latest message into a standalone search query "
    "that includes any context required from the conversation history. "
    "Output ONLY the rewritten query, no preamble, no quotes, no explanation. "
    "Preserve the original language."
)


async def rewrite(history: list[dict], latest_user_text: str) -> str:
    if not history:
        return latest_user_text

    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in history[-10:])
    user_prompt = (
        f"Conversation so far:\n{transcript}\n\n"
        f"Latest user message: {latest_user_text}\n\n"
        "Rewritten standalone query:"
    )
    out = await chat(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
    )
    # Defensive: drop accidental quoting / preamble.
    return out.strip().strip('"').strip("'") or latest_user_text
