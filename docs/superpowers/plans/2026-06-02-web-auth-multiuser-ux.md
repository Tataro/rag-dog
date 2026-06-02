# Web App Auth + Multi-User UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

> **⚠️ FRAMEWORK VERSION WARNING (read first):** This frontend runs **Next.js 16.2.6 / React 19** — newer than your training data, with breaking changes. `frontend/AGENTS.md` is explicit. **Before writing or changing anything that touches a Next.js API** (the `app/` router, `"use client"`/server-component boundaries, `next.config`, env exposure, `middleware`, metadata, fonts), READ the installed guide under `frontend/node_modules/next/dist/docs/01-app/` and follow it. Do NOT assume App-Router conventions from memory. The plan below is concrete for framework-agnostic TypeScript/React, and flags every spot where you must consult the installed docs.

**Goal:** Make the existing Next.js web UI a multi-user client: Google sign-in → backend session JWT, all API calls authenticated, the chat tied to a server-side Conversation, plus an admin-only allowlist screen.

**Architecture:** A small auth layer holds the backend session JWT (issued by `POST /api/auth/google`) in `localStorage` and attaches it as `Authorization: Bearer` on every request; a React auth context gates the app behind a Google sign-in button when there's no valid session. The chat drops the old client-generated `session_id` for the server's `conversation_id`. Admin users get an allowlist management screen.

**Tech Stack:** Next.js 16 (App Router), React 19, TypeScript, Tailwind, Google Identity Services (web), Vitest (for the framework-agnostic units). Backend contract from Plans 1–2: `POST /api/auth/google {id_token}` → `{session_token, user}`; `GET /api/auth/me`; `POST /api/query {text, conversation_id?}`; documents CRUD + `GET /api/documents/{id}/file`; `GET/POST/DELETE /api/admin/allowlist`.

> **Prerequisite:** Plan 1 merged (auth + multi-user backend live). Plan 2 (MinIO) is independent of this plan except the download endpoint — Task 5 here uses it but degrades gracefully if not present. Work on branch `feat/web-auth`.

> **Token storage decision:** the JWT lives in `localStorage` and is sent via the `Authorization` header (consistent with the mobile app's secure-store + header approach, and simplest across the localhost:3000 → localhost:8000 origin split with credentialed CORS already enabled). Trade-off: `localStorage` is readable by XSS. Acceptable at this stage for an internal tool; revisit with httpOnly cookies + a same-origin proxy if the threat model tightens.

---

## Task 1: Auth-aware types and API client (framework-agnostic, tested)

**Files:**
- Modify: `frontend/src/lib/types.ts` (add `User`; query takes `conversationId`)
- Create: `frontend/src/lib/auth-storage.ts` (token + user persistence; replaces `session.ts`)
- Modify: `frontend/src/lib/api.ts` (Authorization header, auth endpoints, admin, download, query by conversation)
- Delete: `frontend/src/lib/session.ts` (obsolete `session_id`)
- Add Vitest: `frontend/package.json`, `frontend/vitest.config.ts`
- Test: `frontend/src/lib/auth-storage.test.ts`, `frontend/src/lib/api.test.ts`

- [x] **Step 1: Add Vitest (framework-agnostic unit runner)**

These units are plain TS, so they don't need the Next runtime. Install:
```bash
cd frontend && pnpm add -D vitest jsdom @vitest/coverage-v8
```
Create `frontend/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { environment: "jsdom", globals: true },
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
});
```
Add to `frontend/package.json` `"scripts"`: `"test": "vitest run"`.

- [x] **Step 2: Extend types**

In `frontend/src/lib/types.ts` add:
```ts
export interface User {
  id: string;
  email: string;
  name: string | null;
  picture: string | null;
  is_admin: boolean;
}

export interface LoginResponse {
  session_token: string;
  user: User;
}

export interface AllowedEmail {
  email: string;
  created_at: string;
}
```

- [x] **Step 3: Write failing tests for the token store**

Create `frontend/src/lib/auth-storage.test.ts`:
```ts
import { beforeEach, describe, expect, it } from "vitest";
import { clearAuth, loadToken, loadUser, saveAuth } from "./auth-storage";
import type { User } from "./types";

const user: User = { id: "u1", email: "a@example.com", name: null, picture: null, is_admin: false };

describe("auth-storage", () => {
  beforeEach(() => localStorage.clear());

  it("returns null when nothing is stored", () => {
    expect(loadToken()).toBeNull();
    expect(loadUser()).toBeNull();
  });

  it("round-trips token and user", () => {
    saveAuth("jwt-123", user);
    expect(loadToken()).toBe("jwt-123");
    expect(loadUser()).toEqual(user);
  });

  it("clears both", () => {
    saveAuth("jwt-123", user);
    clearAuth();
    expect(loadToken()).toBeNull();
    expect(loadUser()).toBeNull();
  });
});
```

- [x] **Step 4: Run it (red)** — `cd frontend && pnpm test` → FAIL (no `auth-storage`).

- [x] **Step 5: Implement the token store**

Create `frontend/src/lib/auth-storage.ts`:
```ts
import type { User } from "./types";

const TOKEN_KEY = "ragdog.session_token";
const USER_KEY = "ragdog.user";

export function saveAuth(token: string, user: User): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function loadToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function loadUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as User) : null;
}

export function clearAuth(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}
```

- [x] **Step 6: Run it (green)** — `pnpm test` → PASS.

- [x] **Step 7: Write failing tests for the API client auth header**

Create `frontend/src/lib/api.test.ts`:
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, UnauthorizedError } from "./api";
import { saveAuth } from "./auth-storage";

const user = { id: "u1", email: "a@example.com", name: null, picture: null, is_admin: true };

describe("api client", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("attaches the bearer token", async () => {
    saveAuth("jwt-xyz", user);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await api.listDocuments();
    const headers = new Headers(fetchMock.mock.calls[0][1].headers);
    expect(headers.get("authorization")).toBe("Bearer jwt-xyz");
  });

  it("throws UnauthorizedError on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 401 })));
    await expect(api.listDocuments()).rejects.toBeInstanceOf(UnauthorizedError);
  });
});
```

- [x] **Step 8: Run it (red)** — `pnpm test` → FAIL.

- [x] **Step 9: Rewrite the API client**

Replace `frontend/src/lib/api.ts` with:
```ts
import { loadToken } from "./auth-storage";
import type { AllowedEmail, DocumentOut, LoginResponse, QueryResponse, User } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class UnauthorizedError extends Error {}

function authHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  const token = loadToken();
  if (token) h.set("authorization", `Bearer ${token}`);
  return h;
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = authHeaders(init?.headers);
  if (init?.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) throw new UnauthorizedError("session expired");
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body || path}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  // auth
  googleLogin: (idToken: string) =>
    http<LoginResponse>("/api/auth/google", { method: "POST", body: JSON.stringify({ id_token: idToken }) }),
  me: () => http<User>("/api/auth/me"),

  // documents
  listDocuments: () => http<DocumentOut[]>("/api/documents"),
  getDocument: (id: string) => http<DocumentOut>(`/api/documents/${id}`),
  deleteDocument: (id: string) => http<void>(`/api/documents/${id}`, { method: "DELETE" }),
  documentFileUrl: (id: string) => `${BASE}/api/documents/${id}/file`, // fetched with auth header below
  downloadDocument: async (id: string): Promise<Blob> => {
    const res = await fetch(`${BASE}/api/documents/${id}/file`, { headers: authHeaders() });
    if (res.status === 401) throw new UnauthorizedError("session expired");
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.blob();
  },
  uploadDocument: async (file: File): Promise<DocumentOut> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/documents`, { method: "POST", body: form, headers: authHeaders() });
    if (res.status === 401) throw new UnauthorizedError("session expired");
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text().catch(() => "")}`);
    return res.json();
  },

  // chat
  query: (text: string, conversationId: string | null) =>
    http<QueryResponse>("/api/query", {
      method: "POST",
      body: JSON.stringify({ text, conversation_id: conversationId }),
    }),

  // admin
  listAllowlist: () => http<AllowedEmail[]>("/api/admin/allowlist"),
  addAllowedEmail: (email: string) =>
    http<AllowedEmail>("/api/admin/allowlist", { method: "POST", body: JSON.stringify({ email }) }),
  removeAllowedEmail: (email: string) =>
    http<void>(`/api/admin/allowlist/${encodeURIComponent(email)}`, { method: "DELETE" }),
};
```

- [x] **Step 10: Delete `session.ts`** — `rm frontend/src/lib/session.ts`. (It's replaced; Task 3 removes its last caller in `ChatThread`.)

- [x] **Step 11: Run it (green)** — `pnpm test` → PASS (all). Then `pnpm exec tsc --noEmit` — expect type errors ONLY in files that still import `session.ts` or call `query(text, sessionId)` (fixed in Task 3). Note them; don't fix here.

- [x] **Step 12: Commit**
```bash
git add frontend/src/lib frontend/vitest.config.ts frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat(web): authenticated API client, token store, Vitest units"
```

---

## Task 2: Google sign-in and the auth gate

> **CONSULT THE INSTALLED DOCS FIRST.** Read `frontend/node_modules/next/dist/docs/01-app/` sections on Client Components / `"use client"`, environment variables (`NEXT_PUBLIC_*` exposure), and how a root provider wraps `children` in `app/layout.tsx` for THIS version. The component logic below is plain React 19 (stable); the only version-sensitive bits are the `"use client"` directive placement and env exposure — verify both against the docs.

**Files:**
- Create: `frontend/src/lib/auth-context.tsx` (React context: user, token, login, logout)
- Create: `frontend/src/components/GoogleSignInButton.tsx`
- Create: `frontend/src/components/AuthGate.tsx`
- Modify: `frontend/src/app/layout.tsx` (wrap children in the provider + gate)
- Modify: `frontend/.env.local` / document `NEXT_PUBLIC_GOOGLE_CLIENT_ID`

- [x] **Step 1: Env + Google client ID**

Create/append `frontend/.env.local` (gitignored) and document in the README:
```
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<your-web-oauth-client-id>.apps.googleusercontent.com
```
The same client ID must be in the backend's `GOOGLE_CLIENT_IDS`.

- [x] **Step 2: Auth context**

Create `frontend/src/lib/auth-context.tsx` (verify `"use client"` placement against the installed docs):
```tsx
"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, UnauthorizedError } from "./api";
import { clearAuth, loadToken, loadUser, saveAuth } from "./auth-storage";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  ready: boolean; // initial localStorage hydration done
  loginWithGoogle: (idToken: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const u = loadUser();
    if (u && loadToken()) {
      setUser(u);
      // Validate the stored token against the backend; clear if rejected.
      api.me().then(setUser).catch((e) => {
        if (e instanceof UnauthorizedError) { clearAuth(); setUser(null); }
      }).finally(() => setReady(true));
    } else {
      setReady(true);
    }
  }, []);

  const loginWithGoogle = useCallback(async (idToken: string) => {
    const { session_token, user } = await api.googleLogin(idToken);
    saveAuth(session_token, user);
    setUser(user);
  }, []);

  const logout = useCallback(() => { clearAuth(); setUser(null); }, []);

  return <Ctx.Provider value={{ user, ready, loginWithGoogle, logout }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used within AuthProvider");
  return v;
}
```
> NOTE: `useCallback` is imported as `useCallback` — fix the import name (`import { createContext, useCallback, useContext, useEffect, useState } from "react"`). Double-check React 19 export names if tsc complains.

- [x] **Step 3: Google sign-in button (Google Identity Services)**

Create `frontend/src/components/GoogleSignInButton.tsx`. Loads the GIS script and renders the Google button; on credential callback, calls `loginWithGoogle(response.credential)` (the credential is the Google ID token).
```tsx
"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@/lib/auth-context";

declare global {
  interface Window { google?: any; }
}

export function GoogleSignInButton() {
  const { loginWithGoogle } = useAuth();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId) { console.error("NEXT_PUBLIC_GOOGLE_CLIENT_ID is not set"); return; }

    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: clientId,
        callback: (resp: { credential: string }) => {
          loginWithGoogle(resp.credential).catch((e) => alert(`Sign-in failed: ${e.message}`));
        },
      });
      if (ref.current) {
        window.google?.accounts.id.renderButton(ref.current, { theme: "outline", size: "large" });
      }
    };
    document.body.appendChild(script);
    return () => { script.remove(); };
  }, [loginWithGoogle]);

  return <div ref={ref} />;
}
```

- [x] **Step 4: Auth gate**

Create `frontend/src/components/AuthGate.tsx`:
```tsx
"use client";

import { useAuth } from "@/lib/auth-context";
import { GoogleSignInButton } from "./GoogleSignInButton";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  if (!ready) return <div className="flex-1 grid place-items-center text-sm text-zinc-500">Loading…</div>;
  if (!user) {
    return (
      <div className="flex-1 grid place-items-center gap-6">
        <div className="text-center">
          <h1 className="text-xl font-semibold mb-1">🐶 rag-dog</h1>
          <p className="text-sm text-zinc-500">Sign in with your Google account to continue.</p>
        </div>
        <GoogleSignInButton />
      </div>
    );
  }
  return <>{children}</>;
}
```

- [x] **Step 5: Wrap the app**

Modify `frontend/src/app/layout.tsx` to wrap the `<main>` content in `AuthProvider` + `AuthGate`. **Consult the installed docs** for whether providers go directly in the server `layout.tsx` (they can, since the provider is a client component) or need a separate `providers.tsx` client wrapper in THIS Next version. Keeping the existing `<Nav />`, the body becomes:
```tsx
<AuthProvider>
  <Nav />
  <main className="flex-1 flex flex-col"><AuthGate>{children}</AuthGate></main>
</AuthProvider>
```
Add the imports. If Next 16 requires providers in a dedicated `"use client"` module imported by the server layout, follow that pattern from the docs instead.

- [x] **Step 6: Verify** — `cd frontend && pnpm exec tsc --noEmit` (fix any React-19 import/type issues), `pnpm lint`, then `pnpm dev` and manually confirm: unauthenticated shows the Google button; signing in renders the app; reload stays signed in; clearing localStorage logs out.

- [x] **Step 7: Commit**
```bash
git add frontend/src/lib/auth-context.tsx frontend/src/components/GoogleSignInButton.tsx frontend/src/components/AuthGate.tsx frontend/src/app/layout.tsx
git commit -m "feat(web): Google sign-in, auth context, and auth gate"
```

---

## Task 3: Wire chat + documents to auth and conversations

**Files:**
- Modify: `frontend/src/components/ChatThread.tsx` (use `conversation_id`, not `session_id`; handle 401)
- Modify: `frontend/src/components/DocumentUploader.tsx` / `DocumentList.tsx` (already use `api.*`; just confirm they get auth via the client — they do — and handle `UnauthorizedError`)
- Add a logout control to `frontend/src/components/Nav.tsx`

- [x] **Step 1: Read the current components** — read `ChatThread.tsx`, `DocumentUploader.tsx`, `DocumentList.tsx` fully. They already call `api.*`, which now carries the token, so most "auth" is automatic. The real change is in `ChatThread`: it imports `getSessionId`/`resetSession` from the deleted `session.ts` and calls `api.query(text, sessionId)`.

- [x] **Step 2: Update `ChatThread`** — remove the `session.ts` import. Keep a React state `conversationId: string | null` (starts `null`). On send, call `api.query(text, conversationId)`; on response, `setConversationId(resp.conversation_id)`. A "New chat" button sets `conversationId` back to `null` and clears the visible turns. Wrap send in try/catch: on `UnauthorizedError`, call `useAuth().logout()` (the gate then shows sign-in). Preserve the existing rendering of turns + citations.

- [x] **Step 3: Add logout to `Nav`** — `Nav` is currently a server component (no hooks). Either make it a client component (`"use client"` — confirm the directive against the installed docs) or extract a small client `<UserMenu />` showing the user's email + a "Sign out" button calling `useAuth().logout()`. Prefer the small client child so `Nav` stays mostly as-is.

- [x] **Step 4: Verify** — `pnpm exec tsc --noEmit` (should now be clean — no more `session.ts` references), `pnpm lint`, `pnpm test`. Manually: send a chat message (works, authenticated), confirm a follow-up reuses the same `conversation_id` (check the network tab), "New chat" starts a fresh one, sign out returns to the gate.

- [x] **Step 5: Commit**
```bash
git add frontend/src/components/ChatThread.tsx frontend/src/components/Nav.tsx
git commit -m "feat(web): chat uses server conversations; nav logout; 401 handling"
```

---

## Task 4: Admin allowlist screen

> **CONSULT THE INSTALLED DOCS** for how to add a new route under `app/` in Next 16 (the existing `chat/` and `documents/` route folders are the pattern to mirror) and how client-side navigation/`Link` works in this version.

**Files:**
- Create: `frontend/src/app/admin/page.tsx`
- Create: `frontend/src/components/AllowlistManager.tsx`
- Modify: `frontend/src/components/Nav.tsx` (show an "Admin" link only when `user.is_admin`)

- [ ] **Step 1: Allowlist manager component** — Create `AllowlistManager.tsx` (`"use client"`): on mount, `api.listAllowlist()`; render the list with a remove button (`api.removeAllowedEmail`); an input + add button (`api.addAllowedEmail`, then refresh). Guard the whole component: if `!useAuth().user?.is_admin`, render "Not authorized." Handle `UnauthorizedError` via `logout()`.

- [ ] **Step 2: Admin page** — Create `frontend/src/app/admin/page.tsx` mirroring `chat/page.tsx`'s structure, rendering `<AllowlistManager />`.

- [ ] **Step 3: Conditional nav link** — In the client `<UserMenu />` (or `Nav`), show an "Admin" `Link` to `/admin` only when `user.is_admin`.

- [ ] **Step 4: Verify** — `tsc --noEmit`, `pnpm lint`, `pnpm test`. Manually: as the bootstrap admin, `/admin` lists/adds/removes emails; as a non-admin (or direct nav), it shows "Not authorized"; the backend also enforces 403 (defense in depth).

- [ ] **Step 5: Commit**
```bash
git add frontend/src/app/admin frontend/src/components/AllowlistManager.tsx frontend/src/components/Nav.tsx
git commit -m "feat(web): admin allowlist management screen"
```

---

## Task 5: Document download wiring + final verification

**Files:**
- Modify: `frontend/src/components/DocumentList.tsx` (download via authenticated blob; uses Plan 2's `/file` endpoint)
- Modify: `README.md` (web env vars: `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID`)

- [ ] **Step 1: Download control** — In `DocumentList`, add a download action calling `api.downloadDocument(id)` → create an object URL from the Blob and trigger a save (`const url = URL.createObjectURL(blob); ...; URL.revokeObjectURL(url)`). If Plan 2 isn't merged yet, this endpoint 404s — guard with a try/catch and a "download unavailable" message so the screen still works.

- [ ] **Step 2: README** — Document the two `NEXT_PUBLIC_*` vars and that the web OAuth client ID must also be in the backend `GOOGLE_CLIENT_IDS`.

- [ ] **Step 3: Full verification**
```bash
cd frontend
pnpm test
pnpm exec tsc --noEmit
pnpm lint
pnpm build   # the real Next 16 production build — must succeed
```
All must pass. Then `pnpm dev` and walk the full flow: sign in → upload a doc → see it ingest to `ready` → chat with a citation → download the doc → (as admin) manage the allowlist → sign out.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/components/DocumentList.tsx README.md
git commit -m "feat(web): authenticated document download; docs"
```

---

## Self-Review (completed during planning)

**Spec coverage:** Google sign-in → backend JWT (Task 2); all calls authenticated incl. upload/download (Task 1); 401 → logout/gate (Tasks 1–3); chat tied to server `conversation_id`, old `session_id` removed (Task 3); admin allowlist UI, admin-only (Task 4); authenticated download via Plan 2's endpoint (Task 5).

**Framework-risk handling:** every Next-16-specific surface (`"use client"`, provider placement, env exposure, new route folders, `Link`) carries an explicit "consult `node_modules/next/dist/docs/01-app/`" instruction rather than assumed-from-memory code. Framework-agnostic logic (token store, API client, query-by-conversation) is fully specified and unit-tested with Vitest.

**Type/name consistency:** `api.googleLogin/me/listDocuments/uploadDocument/downloadDocument/query/listAllowlist/addAllowedEmail/removeAllowedEmail`, `auth-storage.{saveAuth,loadToken,loadUser,clearAuth}`, `useAuth()` → `{user, ready, loginWithGoogle, logout}`, and the `User`/`LoginResponse`/`AllowedEmail` types are used identically across tasks. `query(text, conversationId)` matches the backend's `{text, conversation_id}`.

**Known issues to fix during implementation (flagged, not hidden):** the `auth-context.tsx` snippet imports `useCallback` correctly but double-check the exact React 19 hook export names if tsc complains; the GIS `window.google` is typed `any` (acceptable for the SDK shim). `localStorage` token storage is an accepted XSS trade-off documented above.
