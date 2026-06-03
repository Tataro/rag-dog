# Conversation History Read Endpoints + Client Wiring — Design

**Date:** 2026-06-03
**Status:** Approved (design)

## Problem

Chat history is fully persisted server-side: `answer_query` writes both the user
and assistant `Message` rows per `Conversation` (`backend/app/generation/pipeline.py`),
and history is read back internally to drive query rewriting. But there is **no read
endpoint** exposing it. The API surface is only `POST /api/query` (+ documents/auth/admin).

Consequently both clients (Expo mobile `explore.tsx`, Next.js `ChatThread.tsx`) hold the
conversation entirely in in-memory React state (`turns` + `conversationId`). Reopening the
app or remounting the component loses the *visible* thread, even though the data survives in
Postgres. Users cannot see or resume past conversations.

## Goal

Expose persisted conversations through read endpoints and wire them into both clients so
users can browse and resume past conversations.

Out of scope: editing/deleting/renaming conversations; pagination/search; bot channels
(Telegram/Line are descoped per ADR 0004); any change to how messages are *written*.

## Architecture

### Backend — new `conversations` router

New file `backend/app/api/conversations.py`, registered in `main.py` at `/api/conversations`
with `tags=["conversations"]`. Both endpoints depend on `get_user_session` (the RLS-scoped
session from `deps.py`), so another user's conversation is indistinguishable from a missing
one → 404, exactly mirroring `documents.py`'s `_get_doc_or_404` pattern.

**`GET /api/conversations` → `list[ConversationOut]`**
- Lists the current user's conversations that have **at least one message**. Empty shells
  (a conversation row created in phase 1a whose generation failed before any message was
  persisted) are naturally excluded because `preview` comes from an inner relationship to
  the first user message.
- Ordered by **last activity** (most recent message time) descending — better for a history
  list than creation time.
- `ConversationOut = { id: UUID, preview: str, created_at: datetime, last_message_at: datetime }`
  where `preview` = the conversation's earliest `role='user'` message content, truncated to
  80 chars (with `…` if longer).

**`GET /api/conversations/{id}` → `ConversationDetail`**
- 404 if the id is unknown or owned by another user (RLS).
- `ConversationDetail = { id: UUID, created_at: datetime, messages: list[MessageOut] }`
  with messages in chronological (`created_at` asc) order.
- `MessageOut = { id: UUID, role: str, content: str, citations: list[Citation] | None, created_at: datetime }`.
  `citations` deserializes from the stored JSON column; reuse the existing `Citation` schema.

No DB or migration changes. Preview / `last_message_at` are derived in the query layer:

- `last_message_at`: a correlated scalar subquery `MAX(messages.created_at)` per conversation
  (also used in the `WHERE` to drop messageless conversations, and as the `ORDER BY` key).
- `preview`: the `content` of the earliest message with `role='user'` for that conversation
  (correlated subquery ordered by `created_at` asc, limit 1), truncated in Python.

### Schemas (`backend/app/schemas.py`)

Add `ConversationOut`, `MessageOut`, `ConversationDetail` (Pydantic `BaseModel`s).
`MessageOut` and `ConversationDetail` use `model_config = ConfigDict(from_attributes=True)`
where they map directly off ORM rows; `ConversationOut` is built explicitly from query rows
(preview/last_message_at are not ORM attributes).

### Web frontend (Next.js) — inline sidebar

- `frontend/src/lib/types.ts`: add `ConversationOut`, `MessageOut`, `ConversationDetail`.
- `frontend/src/lib/api.ts`: add `listConversations()` → `ConversationOut[]` and
  `getConversation(id)` → `ConversationDetail`.
- `frontend/src/app/chat/page.tsx`: becomes a two-column flex layout — a new
  **`ChatSidebar`** on the left + the existing `ChatThread` on the right. The page owns the
  shared state: `activeConversationId: string | null` and a `reloadKey: number` used to
  refresh the sidebar.
- **New `frontend/src/components/ChatSidebar.tsx`**: fetches `listConversations()` on mount
  and whenever `reloadKey` changes; renders rows (`preview` + relative time via the existing
  `lib/format.ts`), highlights the row matching `activeConversationId`, and calls
  `onSelect(id)` on click. Contains the **New chat** button (`onSelect(null)`). On `md+` it
  is a fixed left column (~`w-64`); on small screens it collapses behind a toggle so the
  thread stays usable. Surfaces its own load error inline; `UnauthorizedError` → `logout()`.
- **`frontend/src/components/ChatThread.tsx`** changes from self-contained to **controlled**:
  it receives `conversationId: string | null` and `onConversationChange: (id: string) => void`
  as props instead of owning `conversationId` in local state.
  - When `conversationId` changes to a non-null value, it fetches that conversation
    (`getConversation`) and populates `turns` (mapping `MessageOut[]` → `ChatTurn[]`).
  - When it changes to `null`, it clears to an empty thread.
  - After a send resolves, it calls `onConversationChange(res.conversation_id)`. The page
    sets `activeConversationId` to that id and bumps `reloadKey`, so a brand-new conversation
    appears in (and is highlighted by) the sidebar automatically.
- `frontend/src/components/Nav.tsx`: **no change** (no separate route).

### Mobile (Expo) — new History tab

- `mobile/src/lib/types.ts` / `mobile/src/lib/api.ts`: same type + method additions as web
  (the mobile `api` is async/token-aware but the method shapes match).
- **New `mobile/src/app/(app)/history.tsx`**: a `FlatList` of conversations (preview +
  relative time), pull-to-refresh, loading/empty/error states mirroring the Documents screen
  (`index.tsx`) conventions. Tapping a row navigates to the Chat tab passing the conversation
  id as a route param:
  `router.navigate({ pathname: '/explore', params: { c: id } })`.
- `mobile/src/components/app-tabs.tsx`: register the third tab (**History**) alongside the
  existing Documents/Chat tabs (verify the API against the installed `expo-router` types).
- `mobile/src/app/(app)/explore.tsx` (Chat): read `useLocalSearchParams().c`. When it is set
  (and differs from the currently loaded conversation), fetch that conversation and populate
  `turns` + `conversationId`. The existing **New chat** button additionally clears the param
  (navigate to `/explore` with no params) so a reset doesn't immediately reload.

## Data flow

```
List:   client → GET /api/conversations → [{id, preview, created_at, last_message_at}, …]
Resume: client → GET /api/conversations/{id} → {id, created_at, messages:[{role,content,citations,…}]}
        → client maps messages into its existing turn/bubble rendering
Send:   unchanged — POST /api/query {text, conversation_id} → answer persists a new turn;
        client refreshes the conversation list so the new/updated conversation surfaces.
```

## Error handling

- Unknown / cross-user conversation id → **404** (RLS makes it indistinguishable from
  missing), surfaced in clients as a load error; existing `UnauthorizedError` (401) handling
  triggers sign-out as elsewhere.
- Empty conversations (no messages) are omitted from the list by construction.
- `citations` is `None` for assistant turns without citations and for all user turns.

## Testing (TDD)

- **Backend** — `backend/tests/test_conversations_api.py` (httpx `client` + `fake_google` /
  `fake_llm` fixtures, following `test_query_api.py`):
  - empty list for a user with no conversations;
  - after a `/api/query`, list returns one conversation with the expected `preview` and a
    `last_message_at`;
  - ordering by last activity across two conversations;
  - detail returns user+assistant messages in chronological order (and `citations` shape);
  - detail and list isolate users — user B gets 404 on user A's conversation id and an empty
    list (RLS), mirroring `test_cannot_query_into_another_users_conversation`.
- **Web** — extend `frontend/src/lib/api.test.ts`: `listConversations()` attaches the bearer
  token and `getConversation()` raises `UnauthorizedError` on 401.
- **Mobile** — extend `mobile/src/lib/api.test.ts`: same two assertions for the async client.
- Component-level UI wiring (sidebar selection, controlled `ChatThread`, History tab
  navigation) is verified manually via the run/verify skills; no new RN/React render tests
  are introduced beyond the existing suites.

## Consequences / trade-offs

- Making `ChatThread` **controlled** is a small refactor of an existing component (conversation
  state moves up to the chat page), but it keeps the sidebar and thread in sync without
  duplicating conversation state.
- Deriving `preview` per-row uses correlated subqueries. At this app's scale (personal,
  per-user document RAG) this is fine; if conversation counts ever grow large, a denormalized
  `title`/`last_message_at` column would be the follow-up — explicitly deferred (YAGNI).
- No write-path changes, so existing query behavior and tests are unaffected.
