# Domain glossary

Terms that have a specific meaning in this project. Implementation details belong in code, not here.

## User

A human with an identity in the system, established by logging in with Google. Owns private Documents and Conversations that must never be visible to another User. Replaces the original single-user assumption: every Document, Chunk, and Conversation now belongs to exactly one User, and retrieval is always scoped to the asking User.

A User is provisioned only after an Admin has added their email to the allowlist (closed access — no open signup). The first Google sign-in whose verified email matches an allowlisted entry creates the User; sign-ins from non-allowlisted emails are rejected.

## Admin

A User with the privilege to manage the allowlist — adding and removing the emails permitted to become Users. The first Admin is bootstrapped when the system is first set up; thereafter Admins are designated from existing Users.

> The **Conversation** and **Channel** terms below predate the User concept and still describe the single-user model. They will be revised once we resolve how Telegram/Line identities map to a User.

## Document

A file uploaded by a User. Lives on disk under `uploads/` and as a row in the `documents` table. Has a lifecycle: `uploading → processing → ready` (or `failed`). A Document is a unit of upload, not a unit of retrieval. Owned by exactly one User.

## Chunk

A contiguous span of text extracted from a Document during ingestion, paired with its embedding. The unit of retrieval. Each Chunk knows its source Document, position (chunk index), and where it came from inside the original (page for PDFs, header path for Markdown).

## Conversation

A thread of messages between a User and the assistant. Owned by a User and identified by its own id — it is not tied to a device or channel. The same Conversation is visible from all of that User's authenticated clients (web and mobile); starting a chat on mobile and continuing it on web is one Conversation. A User may have many Conversations.

## Channel

A surface through which a User talks to the assistant. The multi-user launch ships two: `web` (the Next.js UI) and `mobile` (the native app). Both are authenticated clients that identify the User via their Google session, so the backend always knows whose Documents to search. The single-user-era `telegram` and `line` bots are descoped pending an account-linking design (deferred) — see ADR 0004 (`docs/adr/0004-multi-user-production-pivot.md`).

## Citation

A reference attached to an assistant Message identifying one Chunk that contributed to the answer. Rendered as a clickable card on the web UI and as a footer line on Telegram/Line. The model is instructed to mark sources inline with `[1]`, `[2]`, …; the backend resolves those markers to Chunk references.

## Query rewriting

The step that takes a follow-up like "and the penalties?" plus the last 5 turns of Conversation, and produces a standalone retrieval query like "What are the penalties in the contract?". Done by the generation LLM. Skipped when there is no prior history.
