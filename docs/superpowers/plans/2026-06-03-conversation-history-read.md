# Conversation History Read Endpoints + Client Wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose persisted conversations through read endpoints and wire them into both the web (Next.js, inline sidebar) and mobile (Expo, History tab) clients so users can browse and resume past conversations.

**Architecture:** A new RLS-scoped `/api/conversations` router lists conversations (with a server-derived preview + last-activity time) and returns a single conversation's messages. Both clients gain `listConversations()`/`getConversation()`. The web `ChatThread` becomes a *controlled* component driven by a sidebar; the mobile app adds a History tab that loads a conversation into the existing Chat screen via a route param. No DB/migration or write-path changes.

**Tech Stack:** FastAPI + SQLAlchemy (async, RLS) + Pydantic on the backend; Next.js (App Router) + Tailwind on web; Expo + `expo-router` (`unstable-native-tabs`) on mobile. Tests: pytest/httpx (backend), vitest (web), jest-expo (mobile).

> **⚠️ SDK CAUTION:** `expo-router`'s native tabs are imported from `expo-router/unstable-native-tabs` and may differ from training data. For the Task 5 navigation/param APIs (`router.navigate`, `useLocalSearchParams`, `router.setParams`, adding a `NativeTabs.Trigger`), consult the **installed** package under `mobile/node_modules/expo-router/` or the current Expo docs (https://docs.expo.dev/versions/v56.0.0/) before finalizing — do not assume signatures from memory.

**Reference spec:** `docs/superpowers/specs/2026-06-03-conversation-history-read-design.md`

---

## File Structure

**Backend**
- Modify `backend/app/schemas.py` — add `ConversationOut`, `MessageOut`, `ConversationDetail`.
- Create `backend/app/api/conversations.py` — the two read endpoints.
- Modify `backend/app/main.py` — register the router.
- Create `backend/tests/test_conversations_api.py` — endpoint tests.

**Web (`frontend/`)**
- Modify `src/lib/types.ts` — add the three interfaces.
- Modify `src/lib/api.ts` — add `listConversations` / `getConversation`.
- Modify `src/lib/api.test.ts` — bearer + 401 tests for the new methods.
- Create `src/components/ChatSidebar.tsx` — conversation list + New chat.
- Modify `src/components/ChatThread.tsx` — make it controlled.
- Modify `src/app/chat/page.tsx` — two-column layout owning shared state.

**Mobile (`mobile/`)**
- Modify `src/lib/types.ts` — add the three interfaces.
- Modify `src/lib/api.ts` — add `listConversations` / `getConversation`.
- Modify `src/lib/api.test.ts` — bearer + 401 tests for the new methods.
- Create `src/app/(app)/history.tsx` — History tab screen.
- Modify `src/app/(app)/explore.tsx` — load a conversation from the `c` route param.
- Modify `src/components/app-tabs.tsx` — register the History tab.

---

## Task 1: Backend — conversation read endpoints

**Files:**
- Modify: `backend/app/schemas.py`
- Create: `backend/app/api/conversations.py`
- Modify: `backend/app/main.py:7` (import) and `:41` (router registration)
- Test: `backend/tests/test_conversations_api.py`

> Run all backend commands from `backend/` (the test DB must be up, as for the existing suite).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_conversations_api.py`:

```python
import pytest
from sqlalchemy import text

from app.api import auth as auth_api
from app.generation import pipeline as gen_pipeline
from app.db import SessionLocal


@pytest.fixture
def fake_google(monkeypatch):
    async def _fake(token: str) -> dict:
        return {"email": token, "email_verified": True, "name": None, "picture": None,
                "aud": "test-client.apps.googleusercontent.com"}
    monkeypatch.setattr(auth_api, "verify_google_id_token", _fake)


@pytest.fixture
def fake_llm(monkeypatch):
    async def _embed(text):
        return [0.0] * 1024
    async def _chat(messages, temperature=0.1):
        return "answer with no citation"
    monkeypatch.setattr(gen_pipeline, "embed_text", _embed)
    monkeypatch.setattr(gen_pipeline, "chat", _chat)


async def _login(client, email: str) -> dict:
    token = (await client.post("/api/auth/google", json={"id_token": email})).json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


async def _allow(email: str) -> None:
    async with SessionLocal() as s:
        await s.execute(text("INSERT INTO allowed_emails (email) VALUES (:e)"), {"e": email})
        await s.commit()


@pytest.mark.asyncio
async def test_list_empty_for_new_user(client, fake_google):
    h = await _login(client, "boss@example.com")
    resp = await client.get("/api/conversations", headers=h)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_returns_preview_after_query(client, fake_google, fake_llm):
    h = await _login(client, "boss@example.com")
    await client.post("/api/query", json={"text": "what is rls"}, headers=h)
    body = (await client.get("/api/conversations", headers=h)).json()
    assert len(body) == 1
    assert body[0]["preview"] == "what is rls"
    assert body[0]["last_message_at"]
    assert body[0]["created_at"]


@pytest.mark.asyncio
async def test_list_ordered_by_last_activity(client, fake_google, fake_llm):
    h = await _login(client, "boss@example.com")
    a = (await client.post("/api/query", json={"text": "first"}, headers=h)).json()["conversation_id"]
    b = (await client.post("/api/query", json={"text": "second"}, headers=h)).json()["conversation_id"]
    # Continue A so it becomes the most-recently-active conversation.
    await client.post("/api/query", json={"text": "again", "conversation_id": a}, headers=h)
    body = (await client.get("/api/conversations", headers=h)).json()
    assert [c["id"] for c in body] == [a, b]


@pytest.mark.asyncio
async def test_detail_returns_messages_in_order(client, fake_google, fake_llm):
    h = await _login(client, "boss@example.com")
    cid = (await client.post("/api/query", json={"text": "hello"}, headers=h)).json()["conversation_id"]
    body = (await client.get(f"/api/conversations/{cid}", headers=h)).json()
    assert body["id"] == cid
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "hello"
    assert body["messages"][1]["content"] == "answer with no citation"
    assert body["messages"][1]["citations"] is None


@pytest.mark.asyncio
async def test_other_user_cannot_read_conversation(client, fake_google, fake_llm):
    h1 = await _login(client, "boss@example.com")
    cid = (await client.post("/api/query", json={"text": "hi"}, headers=h1)).json()["conversation_id"]
    await _allow("m@example.com")
    h2 = await _login(client, "m@example.com")
    assert (await client.get(f"/api/conversations/{cid}", headers=h2)).status_code == 404
    assert (await client.get("/api/conversations", headers=h2)).json() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_conversations_api.py -v`
Expected: FAIL — all error with `404 Not Found` / assertion errors because `/api/conversations` is not registered yet.

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas.py`, after the `Citation` class (it must already be defined above), add:

```python
class ConversationOut(BaseModel):
    id: UUID
    preview: str
    created_at: datetime
    last_message_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    citations: list[Citation] | None = None
    created_at: datetime


class ConversationDetail(BaseModel):
    id: UUID
    created_at: datetime
    messages: list[MessageOut]
```

(`datetime`, `UUID`, `BaseModel`, `ConfigDict` are already imported at the top of the file.)

- [ ] **Step 4: Create the router**

Create `backend/app/api/conversations.py`:

```python
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_user_session
from ..models import Conversation, Message
from ..schemas import ConversationDetail, ConversationOut, MessageOut

router = APIRouter()

_PREVIEW_LEN = 80


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    session: AsyncSession = Depends(get_user_session),
) -> list[ConversationOut]:
    # Correlated subqueries against the outer `conversations` row. RLS scopes both
    # tables to the current user, so no explicit user_id filter is needed here.
    last_at = (
        select(func.max(Message.created_at))
        .where(Message.conversation_id == Conversation.id)
        .scalar_subquery()
    )
    first_user_msg = (
        select(Message.content)
        .where(Message.conversation_id == Conversation.id, Message.role == "user")
        .order_by(Message.created_at.asc())
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        select(Conversation.id, Conversation.created_at, first_user_msg, last_at)
        .where(last_at.is_not(None))  # drop empty conversations (no messages)
        .order_by(last_at.desc())
    )
    rows = (await session.execute(stmt)).all()

    out: list[ConversationOut] = []
    for cid, created_at, preview, last_message_at in rows:
        preview = preview or ""
        if len(preview) > _PREVIEW_LEN:
            preview = preview[: _PREVIEW_LEN - 1] + "…"
        out.append(
            ConversationOut(
                id=cid,
                preview=preview,
                created_at=created_at,
                last_message_at=last_message_at,
            )
        )
    return out


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    session: AsyncSession = Depends(get_user_session),
) -> ConversationDetail:
    # RLS hides other users' conversations → get() returns None → 404 (mirrors documents.py).
    convo = await session.get(Conversation, conversation_id)
    if convo is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = (await session.execute(stmt)).scalars().all()
    return ConversationDetail(
        id=convo.id,
        created_at=convo.created_at,
        messages=[MessageOut.model_validate(m) for m in messages],
    )
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, update the import on line 7:

```python
from .api import admin, auth, conversations, documents, query
```

And add a registration line after the existing `query` router (line 41):

```python
app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_conversations_api.py -v`
Expected: PASS (5 passed).

- [ ] **Step 7: Run the full backend suite (no regressions)**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/api/conversations.py backend/app/main.py backend/tests/test_conversations_api.py
git commit -m "feat(api): conversation history read endpoints

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Web — API client + types

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts:2` (import) and the `api` object
- Test: `frontend/src/lib/api.test.ts`

> Run web commands from `frontend/`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/lib/api.test.ts`, add these two tests inside the `describe("api client", ...)` block (after the existing `it(...)` blocks):

```typescript
  it("listConversations attaches the bearer token", async () => {
    saveAuth("jwt-xyz", user);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await api.listConversations();
    const headers = new Headers(fetchMock.mock.calls[0][1].headers);
    expect(headers.get("authorization")).toBe("Bearer jwt-xyz");
  });

  it("getConversation throws UnauthorizedError on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 401 })));
    await expect(api.getConversation("c1")).rejects.toBeInstanceOf(UnauthorizedError);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test -- src/lib/api.test.ts`
Expected: FAIL — `api.listConversations is not a function` / `api.getConversation is not a function`.

- [ ] **Step 3: Add the types**

In `frontend/src/lib/types.ts`, after the `ChatTurn` interface, add:

```typescript
export interface ConversationOut {
  id: string;
  preview: string;
  created_at: string;
  last_message_at: string;
}

export interface MessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  created_at: string;
  messages: MessageOut[];
}
```

- [ ] **Step 4: Add the API methods**

In `frontend/src/lib/api.ts`, extend the type import on line 2 to include the new types:

```typescript
import type {
  AllowedEmail,
  ConversationDetail,
  ConversationOut,
  DocumentOut,
  LoginResponse,
  QueryResponse,
  User,
} from "./types";
```

Then add these two methods to the `api` object, right after the `query:` method:

```typescript
  listConversations: () => http<ConversationOut[]>("/api/conversations"),
  getConversation: (id: string) => http<ConversationDetail>(`/api/conversations/${id}`),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && pnpm test -- src/lib/api.test.ts`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/lib/api.test.ts
git commit -m "feat(web): conversation history API client methods

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Web — sidebar + controlled ChatThread

**Files:**
- Create: `frontend/src/components/ChatSidebar.tsx`
- Modify: `frontend/src/components/ChatThread.tsx`
- Modify: `frontend/src/app/chat/page.tsx`

No new unit tests (UI wiring is verified manually in Task 6). Each step keeps the app type-checking.

- [ ] **Step 1: Create the sidebar component**

Create `frontend/src/components/ChatSidebar.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { api, UnauthorizedError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatRelative } from "@/lib/format";
import type { ConversationOut } from "@/lib/types";

export function ChatSidebar({
  activeId,
  reloadKey,
  onSelect,
}: {
  activeId: string | null;
  reloadKey: number;
  onSelect: (id: string | null) => void;
}) {
  const { logout } = useAuth();
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await api.listConversations();
        if (!cancelled) {
          setConversations(list);
          setError(null);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UnauthorizedError) {
          logout();
          return;
        }
        setError(err instanceof Error ? err.message : "failed to load history");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, logout]);

  return (
    <aside className="hidden md:flex md:flex-col w-64 shrink-0 border-r border-zinc-200 dark:border-zinc-800 overflow-y-auto">
      <div className="p-3">
        <button
          type="button"
          onClick={() => onSelect(null)}
          className="w-full inline-flex items-center justify-center gap-2 rounded-md border border-zinc-200 dark:border-zinc-800 px-3 py-2 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-900"
        >
          <Plus size={16} />
          New chat
        </button>
      </div>
      {error && <div className="px-3 py-2 text-xs text-rose-600 dark:text-rose-400">{error}</div>}
      <nav className="flex-1 px-2 pb-3 space-y-1">
        {conversations.length === 0 && !error && (
          <p className="px-2 py-4 text-xs text-zinc-500 italic">No conversations yet.</p>
        )}
        {conversations.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => onSelect(c.id)}
            className={`w-full text-left rounded-md px-2 py-2 text-sm transition-colors ${
              c.id === activeId
                ? "bg-zinc-100 dark:bg-zinc-900"
                : "hover:bg-zinc-100/60 dark:hover:bg-zinc-900/60"
            }`}
          >
            <span className="block truncate">{c.preview || "Untitled"}</span>
            <span className="block text-xs text-zinc-500">{formatRelative(c.last_message_at)}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}
```

- [ ] **Step 2: Make `ChatThread` controlled**

Replace the entire contents of `frontend/src/components/ChatThread.tsx` with:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { api, UnauthorizedError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { ChatTurn } from "@/lib/types";
import { CitationCard } from "./CitationCard";

export function ChatThread({
  conversationId,
  onConversationChange,
}: {
  conversationId: string | null;
  onConversationChange: (id: string) => void;
}) {
  const { logout } = useAuth();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // The conversation currently shown in `turns`. Lets us skip a redundant refetch
  // after a send (which bumps `conversationId` to a value we already have loaded).
  const loadedIdRef = useRef<string | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  // Load (or clear) the thread when the selected conversation changes.
  useEffect(() => {
    if (conversationId === loadedIdRef.current) return;

    if (conversationId === null) {
      loadedIdRef.current = null;
      setTurns([]);
      setError(null);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const convo = await api.getConversation(conversationId);
        if (cancelled) return;
        loadedIdRef.current = conversationId;
        setTurns(
          convo.messages.map((m) => ({
            role: m.role,
            content: m.content,
            citations: m.citations ?? undefined,
          })),
        );
        setError(null);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UnauthorizedError) {
          logout();
          return;
        }
        setError(err instanceof Error ? err.message : "failed to load conversation");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId, logout]);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    setBusy(true);
    setError(null);
    setInput("");
    const next = [...turns, { role: "user", content: text } as ChatTurn];
    setTurns(next);

    try {
      const res = await api.query(text, conversationId);
      loadedIdRef.current = res.conversation_id; // we already hold this conversation's turns
      setTurns([...next, { role: "assistant", content: res.answer, citations: res.citations }]);
      onConversationChange(res.conversation_id);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        logout();
        return;
      }
      setError(err instanceof Error ? err.message : "query failed");
      setTurns(next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        {turns.length === 0 && (
          <div className="text-center text-zinc-500 italic text-sm mt-12">
            Ask anything about your uploaded documents.
          </div>
        )}
        {turns.map((t, i) => (
          <Turn key={i} turn={t} />
        ))}
        {busy && (
          <div className="text-sm text-zinc-500 italic flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-zinc-400 animate-pulse" />
            thinking…
          </div>
        )}
        {error && <div className="text-sm text-rose-600 dark:text-rose-400">{error}</div>}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSend}
        className="border-t border-zinc-200 dark:border-zinc-800 px-4 py-3 flex items-end gap-2 bg-white dark:bg-zinc-950"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSend(e as unknown as React.FormEvent);
            }
          }}
          rows={1}
          placeholder="Ask a question…"
          className="flex-1 resize-none rounded-md border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:focus:ring-zinc-100/10"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="p-2 rounded-md bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 disabled:opacity-40"
          title="Send"
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}

function Turn({ turn }: { turn: ChatTurn }) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 px-4 py-2 text-sm whitespace-pre-wrap">
          {turn.content}
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed">
        <ReactMarkdown>{turn.content}</ReactMarkdown>
      </div>
      {turn.citations && turn.citations.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {turn.citations.map((c) => (
            <CitationCard key={c.chunk_id} citation={c} />
          ))}
        </div>
      )}
    </div>
  );
}
```

Note: the in-thread reset button (`RotateCcw`) is intentionally removed — "New chat" now lives in the sidebar.

- [ ] **Step 3: Update the chat page to the two-column layout**

Replace the entire contents of `frontend/src/app/chat/page.tsx` with:

```tsx
"use client";

import { useState } from "react";
import { ChatSidebar } from "@/components/ChatSidebar";
import { ChatThread } from "@/components/ChatThread";

export default function ChatPage() {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  function handleConversationChange(id: string) {
    setActiveConversationId(id);
    // Bump so the sidebar refetches — a brand-new conversation then appears + highlights.
    setReloadKey((k) => k + 1);
  }

  return (
    <div className="flex-1 flex w-full min-h-0">
      <ChatSidebar
        activeId={activeConversationId}
        reloadKey={reloadKey}
        onSelect={setActiveConversationId}
      />
      <div className="flex-1 flex flex-col max-w-3xl mx-auto w-full min-h-0">
        <ChatThread
          conversationId={activeConversationId}
          onConversationChange={handleConversationChange}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Type-check and lint**

Run: `cd frontend && pnpm exec tsc --noEmit && pnpm lint`
Expected: no type errors; lint passes (no unused `RotateCcw`/`confirm` references remain).

- [ ] **Step 5: Run the web test suite (no regressions)**

Run: `cd frontend && pnpm test`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ChatSidebar.tsx frontend/src/components/ChatThread.tsx frontend/src/app/chat/page.tsx
git commit -m "feat(web): conversation history sidebar with resumable threads

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Mobile — API client + types

**Files:**
- Modify: `mobile/src/lib/types.ts`
- Modify: `mobile/src/lib/api.ts:3` (import) and the `api` object
- Test: `mobile/src/lib/api.test.ts`

> Run mobile commands from `mobile/`.

- [ ] **Step 1: Write the failing tests**

In `mobile/src/lib/api.test.ts`, add two tests after the existing ones:

```typescript
test("listConversations attaches bearer token", async () => {
  await saveToken("jwt-xyz");
  const fetchMock = jest.fn().mockResolvedValue(
    new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } }),
  );
  global.fetch = fetchMock as unknown as typeof fetch;
  await api.listConversations();
  const headers = new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers);
  expect(headers.get("authorization")).toBe("Bearer jwt-xyz");
});

test("getConversation throws UnauthorizedError on 401", async () => {
  global.fetch = jest.fn().mockResolvedValue(new Response("", { status: 401 })) as unknown as typeof fetch;
  await expect(api.getConversation("c1")).rejects.toBeInstanceOf(UnauthorizedError);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd mobile && pnpm test -- src/lib/api.test.ts`
Expected: FAIL — `api.listConversations is not a function` / `api.getConversation is not a function`.

- [ ] **Step 3: Add the types**

In `mobile/src/lib/types.ts`, append (matching the file's compact one-line style):

```typescript
export interface ConversationOut { id: string; preview: string; created_at: string; last_message_at: string; }
export interface MessageOut { id: string; role: "user" | "assistant"; content: string; citations: Citation[] | null; created_at: string; }
export interface ConversationDetail { id: string; created_at: string; messages: MessageOut[]; }
```

- [ ] **Step 4: Add the API methods**

In `mobile/src/lib/api.ts`, extend the type import on line 3:

```typescript
import type { ConversationDetail, ConversationOut, DocumentOut, LoginResponse, QueryResponse, User } from "./types";
```

Then add these methods to the `api` object, right after the `query:` method:

```typescript
  listConversations: () => http<ConversationOut[]>("/api/conversations"),
  getConversation: (id: string) => http<ConversationDetail>(`/api/conversations/${id}`),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd mobile && pnpm test -- src/lib/api.test.ts`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add mobile/src/lib/types.ts mobile/src/lib/api.ts mobile/src/lib/api.test.ts
git commit -m "feat(mobile): conversation history API client methods

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Mobile — History tab + Chat param loading

**Files:**
- Create: `mobile/src/app/(app)/history.tsx`
- Modify: `mobile/src/app/(app)/explore.tsx`
- Modify: `mobile/src/components/app-tabs.tsx`

> **Verify expo-router APIs against the installed package** (`mobile/node_modules/expo-router/`): `useLocalSearchParams`, `router.navigate({ pathname, params })`, `router.setParams`, and adding a `NativeTabs.Trigger`. The code below follows the patterns already used in this app but native tabs are flagged "unstable".

- [ ] **Step 1: Create the History screen**

Create `mobile/src/app/(app)/history.tsx`:

```tsx
import { router } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/lib/auth-context';
import { api, UnauthorizedError } from '@/lib/api';
import type { ConversationOut } from '@/lib/types';

function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

export default function HistoryScreen() {
  const { signOut } = useAuth();
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signOutRef = useRef(signOut);
  useEffect(() => {
    signOutRef.current = signOut;
  });

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      setConversations(await api.listConversations());
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        signOutRef.current();
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to load conversations');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await load(true);
    setRefreshing(false);
  }, [load]);

  const openConversation = useCallback((id: string) => {
    router.navigate({ pathname: '/explore', params: { c: id } });
  }, []);

  const renderEmpty = () => {
    if (loading) return null;
    return (
      <ThemedView style={styles.emptyContainer}>
        <ThemedText type="default" themeColor="textSecondary" style={styles.emptyText}>
          No conversations yet. Start one in the Chat tab.
        </ThemedText>
      </ThemedView>
    );
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        <ThemedView style={styles.header}>
          <ThemedText type="subtitle">History</ThemedText>
        </ThemedView>

        {error && (
          <ThemedView type="backgroundElement" style={styles.errorBanner}>
            <ThemedText type="small" style={styles.errorText}>
              {error}
            </ThemedText>
            <Pressable onPress={() => load()}>
              <ThemedText type="small" style={styles.retryText}>
                Retry
              </ThemedText>
            </Pressable>
          </ThemedView>
        )}

        {loading && conversations.length === 0 ? (
          <ThemedView style={styles.loadingContainer}>
            <ActivityIndicator size="large" />
          </ThemedView>
        ) : (
          <FlatList<ConversationOut>
            data={conversations}
            keyExtractor={(item) => item.id}
            renderItem={({ item }) => (
              <Pressable
                onPress={() => openConversation(item.id)}
                style={({ pressed }) => pressed && styles.pressed}
                accessibilityRole="button"
                accessibilityLabel={`Open conversation: ${item.preview}`}>
                <ThemedView type="backgroundElement" style={styles.row}>
                  <ThemedText type="default" numberOfLines={1}>
                    {item.preview || 'Untitled'}
                  </ThemedText>
                  <ThemedText type="small" themeColor="textSecondary">
                    {formatRelative(item.last_message_at)}
                  </ThemedText>
                </ThemedView>
              </Pressable>
            )}
            ListEmptyComponent={renderEmpty}
            contentContainerStyle={styles.listContent}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
            ItemSeparatorComponent={() => <View style={styles.separator} />}
          />
        )}
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, flexDirection: 'row', justifyContent: 'center' },
  safeArea: {
    flex: 1,
    maxWidth: MaxContentWidth,
    paddingHorizontal: Spacing.three,
    paddingBottom: BottomTabInset + Spacing.three,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: Spacing.three,
  },
  pressed: { opacity: 0.7 },
  errorBanner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.two,
    borderRadius: Spacing.two,
    marginBottom: Spacing.two,
  },
  errorText: { color: '#ef4444', flex: 1 },
  retryText: { color: '#3c87f7', marginLeft: Spacing.two },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  listContent: { flexGrow: 1, paddingBottom: Spacing.four },
  separator: { height: Spacing.two },
  row: { padding: Spacing.three, borderRadius: Spacing.three, gap: Spacing.one },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: Spacing.four,
  },
  emptyText: { textAlign: 'center' },
});
```

- [ ] **Step 2: Load a conversation from the route param in the Chat screen**

In `mobile/src/app/(app)/explore.tsx`, update the import from `expo-router` (line 1 currently imports nothing from it — it does not yet). Add at the top with the other imports:

```tsx
import { router, useLocalSearchParams } from 'expo-router';
```

Then, inside `ChatScreen`, just after the existing state declarations (after the `flatListRef` line), add the param-driven loader:

```tsx
  const { c } = useLocalSearchParams<{ c?: string }>();
  // Tracks which conversation `turns` currently reflects, so we don't refetch a
  // conversation we already hold (e.g. right after sending a message).
  const loadedIdRef = useRef<string | null>(null);

  useEffect(() => {
    const id = typeof c === 'string' && c.length > 0 ? c : null;
    if (id === null || id === loadedIdRef.current) return;

    let cancelled = false;
    (async () => {
      try {
        const convo = await api.getConversation(id);
        if (cancelled) return;
        loadedIdRef.current = id;
        setConversationId(id);
        setTurns(
          convo.messages.map((m) => ({
            role: m.role,
            content: m.content,
            citations: m.citations ?? undefined,
          }))
        );
        setError(null);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UnauthorizedError) {
          signOutRef.current();
          return;
        }
        setError(err instanceof Error ? err.message : 'Failed to load conversation');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [c]);
```

In `handleSend`, after `setConversationId(res.conversation_id);`, record the loaded id so navigating back from History to the same conversation doesn't wipe local turns:

```tsx
      loadedIdRef.current = res.conversation_id;
      setConversationId(res.conversation_id);
```

In `handleNewChat`, clear the route param and the loaded-id tracker alongside the existing resets:

```tsx
  const handleNewChat = useCallback(() => {
    if (busy) return;
    loadedIdRef.current = null;
    router.setParams({ c: '' });
    setConversationId(null);
    setTurns([]);
    setError(null);
    setInput('');
  }, [busy]);
```

- [ ] **Step 3: Register the History tab**

In `mobile/src/components/app-tabs.tsx`, add a third `NativeTabs.Trigger` after the `explore` trigger (reusing the existing `explore.png` icon — swap for a dedicated icon later):

```tsx
      <NativeTabs.Trigger name="history">
        <NativeTabs.Trigger.Label>History</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon
          src={require('@/assets/images/tabIcons/explore.png')}
          renderingMode="template"
        />
      </NativeTabs.Trigger>
```

- [ ] **Step 4: Type-check and lint**

Run: `cd mobile && pnpm exec tsc --noEmit && pnpm lint`
Expected: no type errors; lint passes.

- [ ] **Step 5: Run the mobile test suite (no regressions)**

Run: `cd mobile && pnpm test`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add mobile/src/app/(app)/history.tsx mobile/src/app/(app)/explore.tsx mobile/src/components/app-tabs.tsx
git commit -m "feat(mobile): History tab to browse and resume conversations

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Manual verification (web + mobile)

**Files:** none (uses the `verify` / `run` skills).

- [ ] **Step 1: Backend up** — Ensure the backend + DB are running and reachable (web at `http://localhost:8000`; mobile via LAN IP per `mobile` config).

- [ ] **Step 2: Web** — Run `cd frontend && pnpm dev`, sign in, and verify:
  - Sending a message creates a conversation that appears in the left sidebar with the correct preview + relative time.
  - Clicking a different sidebar item loads that conversation's full message thread (including citations).
  - "New chat" clears the thread; sending then adds a new sidebar entry that becomes highlighted.
  - Reloading the browser and clicking a conversation restores its messages (proving DB-backed, not client memory).

- [ ] **Step 3: Mobile** — Launch the dev build (`cd mobile && npx expo start`, open on device/simulator), sign in, and verify:
  - The bottom tab bar shows Documents / Chat / **History**.
  - Sending a message in Chat, then opening History, lists the conversation; tapping it returns to Chat with the full thread loaded.
  - "New chat" in Chat starts an empty thread (and tapping a History item afterward still loads correctly).

- [ ] **Step 4: Note any issues** — If the native-tabs param navigation (Task 5) misbehaves on the installed `expo-router`, capture the exact symptom and adjust using the installed package's docs (e.g. `router.push` vs `router.navigate`, or a `Stack` param route) before considering the task done.

---

## Self-Review Notes

- **Spec coverage:** backend list+detail endpoints + schemas (Task 1); web types/api (Task 2) + sidebar/controlled thread (Task 3); mobile types/api (Task 4) + History tab/param loading (Task 5); TDD tests in Tasks 1/2/4; manual UI verification in Task 6. Preview truncation (80) and ordering-by-last-activity are implemented in Task 1.
- **Type consistency:** `ConversationOut { id, preview, created_at, last_message_at }`, `MessageOut { id, role, content, citations, created_at }`, `ConversationDetail { id, created_at, messages }` are identical across backend schemas, web types, and mobile types. `listConversations()` / `getConversation(id)` signatures match in both clients. `ChatThread` props (`conversationId`, `onConversationChange`) match the chat page usage.
- **Deferred (YAGNI):** no `title` column/migration, no pagination/search, no delete/rename — all explicitly out of scope per the spec.
