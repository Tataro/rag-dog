# Domain glossary

Terms that have a specific meaning in this project. Implementation details belong in code, not here.

## Document

A file uploaded by the user. Lives on disk under `uploads/` and as a row in the `documents` table. Has a lifecycle: `uploading → processing → ready` (or `failed`). A Document is a unit of upload, not a unit of retrieval.

## Chunk

A contiguous span of text extracted from a Document during ingestion, paired with its embedding. The unit of retrieval. Each Chunk knows its source Document, position (chunk index), and where it came from inside the original (page for PDFs, header path for Markdown).

## Conversation

A continuous thread of messages between the user and the assistant on a single channel. Keyed by `(channel, external_id)` — e.g. `(telegram, 123456789)` is one Conversation, `(line, U abc…)` is another. Conversations on different channels are independent even though the underlying user is the same human; we don't link them in v1.

## Channel

A surface through which the user talks to the assistant. Three channels exist: `web` (the Next.js UI), `telegram`, `line`. Each Channel is responsible for translating its native message format to/from the shared query pipeline.

## Citation

A reference attached to an assistant Message identifying one Chunk that contributed to the answer. Rendered as a clickable card on the web UI and as a footer line on Telegram/Line. The model is instructed to mark sources inline with `[1]`, `[2]`, …; the backend resolves those markers to Chunk references.

## Query rewriting

The step that takes a follow-up like "and the penalties?" plus the last 5 turns of Conversation, and produces a standalone retrieval query like "What are the penalties in the contract?". Done by the generation LLM. Skipped when there is no prior history.
