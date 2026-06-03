# Mobile App (React Native + Expo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

> **⚠️ SDK VERSION CAUTION (read first):** Expo and its native modules move fast and may differ from your training data. Scaffold with the **current** `create-expo-app`, and for every native/Expo-specific API (`expo-router`, `expo-secure-store`, `expo-document-picker`, `@react-native-google-signin/google-signin`, EAS config) consult the **installed package's** docs/types (under `mobile/node_modules/<pkg>/`) or the official current docs — do NOT assume signatures from memory. The plan keeps the framework-agnostic TypeScript (token store, API client, auth flow logic) concrete and unit-tested; it flags every native/Expo touch-point for verification.

**Goal:** A React Native (Expo) app — login with Google, upload documents, and chat over them — talking to the same authenticated backend as the web app, with the session token in device secure storage.

**Architecture:** Expo (managed workflow + dev client) with `expo-router` for navigation. Native Google sign-in (`@react-native-google-signin/google-signin`) yields a Google **ID token** sent to `POST /api/auth/google`; the returned session JWT is kept in `expo-secure-store` (Keychain/Keystore) and attached as `Authorization: Bearer` on every request. The same backend contract as the web app: documents CRUD, `POST /api/query {text, conversation_id?}`. Admin management stays web-only — mobile is the end-user surface (upload + chat).

**Tech Stack:** Expo SDK (current), React Native, TypeScript, `expo-router`, `expo-secure-store`, `expo-document-picker`, `@react-native-google-signin/google-signin` (+ its Expo config plugin), `jest-expo` + `@testing-library/react-native` for tests. EAS Build for dev/distribution (the Google native module does NOT run in Expo Go).

> **Prerequisites:** Plan 1 merged (backend auth + multi-user). Helpful but not required: Plans 2–3. Work in a NEW top-level `mobile/` directory on branch `feat/mobile-app`. The backend must be reachable from the device/simulator (use the machine's LAN IP, not `localhost`, on a physical device).

> **Google config dependency:** the mobile sign-in must produce an ID token whose audience the backend accepts. With `@react-native-google-signin`, configure `webClientId` (the OAuth **web** client ID); that becomes the ID token audience. Add that same client ID to the backend's `GOOGLE_CLIENT_IDS`. iOS/Android also need their own OAuth client IDs registered in Google Cloud + the reversed-client-id URL scheme (per the library docs).

---

## Task 1: Scaffold the Expo app

**Files:** new `mobile/` project tree.

- [x] **Step 1: Create the app** — From the repo root:
```bash
cd /Users/kittitatupaphong/Codes/github.com/tataro/rag-dog
pnpm create expo-app@latest mobile --template
```
Choose the TypeScript + expo-router template (the default "Navigation (TypeScript)" template). Confirm `mobile/app/` exists (expo-router file-based routing). Verify the version: `cd mobile && npx expo --version`.

- [x] **Step 2: Add dependencies** — Use `npx expo install` (it picks SDK-compatible versions; do NOT hand-pin):
```bash
cd mobile
npx expo install expo-secure-store expo-document-picker expo-constants
npx expo install @react-native-google-signin/google-signin
```
For tests:
```bash
pnpm add -D jest jest-expo @testing-library/react-native @types/jest
```
Add to `mobile/package.json` `"scripts"`: `"test": "jest"`, and a `"jest"` field: `{ "preset": "jest-expo" }`.

- [x] **Step 3: Configure the Google sign-in config plugin** — In `mobile/app.json` (or `app.config.ts`), add `@react-native-google-signin/google-signin` to `plugins` and set the iOS URL scheme per the **installed library docs** (read `mobile/node_modules/@react-native-google-signin/google-signin/README.md`). Also add an `extra` block for runtime config consumed via `expo-constants`:
```jsonc
{
  "expo": {
    "plugins": ["@react-native-google-signin/google-signin"],
    "extra": {
      "apiBase": "http://192.168.1.x:8000",        // your machine's LAN IP for devices
      "googleWebClientId": "<web-oauth-client-id>.apps.googleusercontent.com",
      "googleIosClientId": "<ios-oauth-client-id>.apps.googleusercontent.com"
    }
  }
}
```
> CONSULT the library README for the exact plugin options and whether `iosUrlScheme` must be passed as a plugin arg in this version.

- [x] **Step 4: Verify the skeleton runs** — `cd mobile && npx expo start` boots the dev server without errors (you don't need a device yet; just confirm no config errors). Then `pnpm test` (jest-expo) — the template may ship a sample test; confirm the runner works (or that there are simply no tests yet).

- [x] **Step 5: Commit**
```bash
git add mobile
git commit -m "feat(mobile): scaffold Expo app (router, secure-store, google-signin, jest)"
```

---

## Task 2: Config, secure token store, and API client (framework-agnostic, tested)

**Files:**
- Create: `mobile/src/lib/config.ts`, `mobile/src/lib/auth-storage.ts`, `mobile/src/lib/api.ts`, `mobile/src/lib/types.ts`
- Test: `mobile/src/lib/auth-storage.test.ts`, `mobile/src/lib/api.test.ts`

- [x] **Step 1: Types + config**

`mobile/src/lib/types.ts` — mirror the backend contract:
```ts
export type DocumentStatus = "uploading" | "processing" | "ready" | "failed";
export interface DocumentOut {
  id: string; filename: string; mime_type: string; size_bytes: number;
  status: DocumentStatus; error: string | null; page_count: number | null;
  created_at: string; indexed_at: string | null;
}
export interface Citation {
  marker: number; chunk_id: string; document_id: string; filename: string;
  page: number | null; section: string | null; snippet: string;
}
export interface QueryResponse { answer: string; citations: Citation[]; conversation_id: string; }
export interface User { id: string; email: string; name: string | null; picture: string | null; is_admin: boolean; }
export interface LoginResponse { session_token: string; user: User; }
```
`mobile/src/lib/config.ts` — read from `expo-constants` `extra`:
```ts
import Constants from "expo-constants";

const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, string>;
export const config = {
  apiBase: extra.apiBase ?? "http://localhost:8000",
  googleWebClientId: extra.googleWebClientId ?? "",
  googleIosClientId: extra.googleIosClientId ?? "",
};
```

- [x] **Step 2: Failing test for the token store** (mock `expo-secure-store`)

`mobile/src/lib/auth-storage.test.ts`:
```ts
const store: Record<string, string> = {};
jest.mock("expo-secure-store", () => ({
  setItemAsync: jest.fn(async (k: string, v: string) => { store[k] = v; }),
  getItemAsync: jest.fn(async (k: string) => store[k] ?? null),
  deleteItemAsync: jest.fn(async (k: string) => { delete store[k]; }),
}));

import { clearToken, loadToken, saveToken } from "./auth-storage";

beforeEach(() => { for (const k of Object.keys(store)) delete store[k]; });

test("round-trips the token", async () => {
  expect(await loadToken()).toBeNull();
  await saveToken("jwt-1");
  expect(await loadToken()).toBe("jwt-1");
  await clearToken();
  expect(await loadToken()).toBeNull();
});
```

- [x] **Step 3: Run (red)** — `cd mobile && pnpm test` → FAIL.

- [x] **Step 4: Implement the secure token store**

`mobile/src/lib/auth-storage.ts`:
```ts
import * as SecureStore from "expo-secure-store";

const TOKEN_KEY = "ragdog_session_token";

export async function saveToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}
export async function loadToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}
export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}
```
> CONSULT `expo-secure-store` docs for any required options (e.g. `keychainAccessible`) for your distribution target.

- [x] **Step 5: Failing test for the API client**

`mobile/src/lib/api.test.ts`:
```ts
const store: Record<string, string> = {};
jest.mock("expo-secure-store", () => ({
  setItemAsync: jest.fn(async (k: string, v: string) => { store[k] = v; }),
  getItemAsync: jest.fn(async (k: string) => store[k] ?? null),
  deleteItemAsync: jest.fn(async (k: string) => { delete store[k]; }),
}));
jest.mock("expo-constants", () => ({ expoConfig: { extra: { apiBase: "http://test" } } }));

import { api, UnauthorizedError } from "./api";
import { saveToken } from "./auth-storage";

afterEach(() => jest.restoreAllMocks());

test("attaches bearer token", async () => {
  await saveToken("jwt-xyz");
  const fetchMock = jest.fn().mockResolvedValue(
    new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } }),
  );
  global.fetch = fetchMock as unknown as typeof fetch;
  await api.listDocuments();
  const headers = new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers);
  expect(headers.get("authorization")).toBe("Bearer jwt-xyz");
});

test("throws UnauthorizedError on 401", async () => {
  global.fetch = jest.fn().mockResolvedValue(new Response("", { status: 401 })) as unknown as typeof fetch;
  await expect(api.listDocuments()).rejects.toBeInstanceOf(UnauthorizedError);
});
```

- [x] **Step 6: Run (red)** — `pnpm test` → FAIL.

- [x] **Step 7: Implement the API client**

`mobile/src/lib/api.ts`:
```ts
import { config } from "./config";
import { loadToken } from "./auth-storage";
import type { DocumentOut, LoginResponse, QueryResponse, User } from "./types";

export class UnauthorizedError extends Error {}

async function authHeaders(extra?: HeadersInit): Promise<Headers> {
  const h = new Headers(extra);
  const token = await loadToken();
  if (token) h.set("authorization", `Bearer ${token}`);
  return h;
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await authHeaders(init?.headers);
  if (init?.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  const res = await fetch(`${config.apiBase}${path}`, { ...init, headers });
  if (res.status === 401) throw new UnauthorizedError("session expired");
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text().catch(() => "")}`);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  googleLogin: (idToken: string) =>
    http<LoginResponse>("/api/auth/google", { method: "POST", body: JSON.stringify({ id_token: idToken }) }),
  me: () => http<User>("/api/auth/me"),
  listDocuments: () => http<DocumentOut[]>("/api/documents"),
  deleteDocument: (id: string) => http<void>(`/api/documents/${id}`, { method: "DELETE" }),
  query: (text: string, conversationId: string | null) =>
    http<QueryResponse>("/api/query", { method: "POST", body: JSON.stringify({ text, conversation_id: conversationId }) }),
  uploadDocument: async (file: { uri: string; name: string; mimeType: string }): Promise<DocumentOut> => {
    const form = new FormData();
    // React Native FormData file shape: { uri, name, type }
    form.append("file", { uri: file.uri, name: file.name, type: file.mimeType } as unknown as Blob);
    const headers = await authHeaders();
    const res = await fetch(`${config.apiBase}/api/documents`, { method: "POST", body: form, headers });
    if (res.status === 401) throw new UnauthorizedError("session expired");
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  },
};
```
> NOTE the RN-specific multipart file shape (`{ uri, name, type }`) — this is the React Native `FormData` convention, NOT a browser `File`. Verify against the installed RN version if upload fails.

- [x] **Step 8: Run (green)** — `pnpm test` → PASS (all). Then `npx tsc --noEmit` — clean.

- [x] **Step 9: Commit**
```bash
git add mobile/src/lib mobile/package.json
git commit -m "feat(mobile): config, secure token store, authenticated API client"
```

---

## Task 3: Native Google sign-in + auth gate + routing

> CONSULT the installed `@react-native-google-signin/google-signin` README and `expo-router` docs for current APIs (configure/signIn shape, how to gate routes / use a root layout in this version).

**Files:**
- Create: `mobile/src/lib/auth-context.tsx`
- Modify: `mobile/app/_layout.tsx` (wrap in provider; gate)
- Create: `mobile/app/login.tsx` (or gate within the layout)

- [x] **Step 1: Auth context** — `mobile/src/lib/auth-context.tsx`: a React context exposing `{ user, ready, signIn(), signOut() }`. On mount, read `loadToken()`; if present, call `api.me()` to validate (clear on `UnauthorizedError`). `signIn()`:
```ts
// pseudocode — verify exact calls against the installed library:
GoogleSignin.configure({ webClientId: config.googleWebClientId, iosClientId: config.googleIosClientId });
await GoogleSignin.hasPlayServices();
const { idToken } = await GoogleSignin.signIn();   // shape may be { data: { idToken } } in newer versions — CHECK
const { session_token, user } = await api.googleLogin(idToken);
await saveToken(session_token);
setUser(user);
```
`signOut()`: `await clearToken(); await GoogleSignin.signOut().catch(()=>{}); setUser(null);`. Handle the case where `idToken` is null (configuration error → surface a clear message).

- [x] **Step 2: Gate + routing** — Using `expo-router`: in `mobile/app/_layout.tsx`, wrap the navigator in `<AuthProvider>` and redirect based on auth state (unauthenticated → a `login` screen with a Google button; authenticated → the tabs/stack). **Follow the installed expo-router docs** for the current redirect/guard pattern (e.g. `<Redirect>`, `useRouter`, or a protected group). Keep a simple login screen that calls `useAuth().signIn()`.

- [x] **Step 3: Verify on a dev build** — The Google native module needs a dev build (not Expo Go):
```bash
cd mobile && npx expo run:ios   # or run:android, or an EAS dev build
```
Confirm: launching shows the login screen; Google sign-in completes; the app lands on the authenticated screens; relaunch stays signed in (token in secure-store); sign-out returns to login. If you cannot run a device build in this environment, STOP and report — auth cannot be verified by unit tests alone.

- [x] **Step 4: Commit**
```bash
git add mobile/src/lib/auth-context.tsx mobile/app
git commit -m "feat(mobile): native Google sign-in, auth context, routing gate"
```

---

## Task 4: Documents screen (list + upload)

> CONSULT `expo-document-picker` installed docs for the current `getDocumentAsync` result shape (it changed across SDKs — `result.assets[0]` vs `result.uri`).

**Files:**
- Create: `mobile/app/(app)/documents.tsx` (or your authenticated route group)
- Create: `mobile/src/components/DocumentRow.tsx` (optional)

- [x] **Step 1: Documents screen** — On focus, `api.listDocuments()` into state; render a `FlatList` of filename + `status` (badge), pull-to-refresh. An "Upload" button calls `expo-document-picker`'s `getDocumentAsync({ type: [...] })`; from the result asset, pass `{ uri, name, mimeType }` to `api.uploadDocument(...)`, then refresh the list. Poll or pull-to-refresh to watch `uploading → processing → ready`. A delete action calls `api.deleteDocument(id)`. Handle `UnauthorizedError` → `useAuth().signOut()`.

- [x] **Step 2: Verify** — `npx tsc --noEmit`, `pnpm test`. On the dev build: pick a PDF/markdown, confirm it uploads and reaches `ready`, appears in the web app's list for the same user (cross-client check), and delete works.

- [x] **Step 3: Commit**
```bash
git add mobile/app mobile/src/components
git commit -m "feat(mobile): documents screen with upload, status, delete"
```

---

## Task 5: Chat screen

**Files:**
- Create: `mobile/app/(app)/chat.tsx`
- Create: `mobile/src/components/Citation.tsx` (optional)

- [x] **Step 1: Chat screen** — Keep `conversationId: string | null` in state (starts `null`) and a list of turns. On send: optimistic append of the user turn, `api.query(text, conversationId)`, append the assistant answer + citations, `setConversationId(resp.conversation_id)`. A "New chat" control resets `conversationId` to `null` and clears turns. Render citations as tappable cards showing `filename` + `snippet` (+ page/section). Handle `UnauthorizedError` → `signOut()`. Use a `KeyboardAvoidingView` + `FlatList` (inverted or auto-scroll to bottom).

- [x] **Step 2: Verify** — `npx tsc --noEmit`, `pnpm test`. On the dev build: ask a question about an uploaded doc, get an answer with at least one citation; a follow-up reuses the same `conversation_id`; "New chat" starts fresh.

- [x] **Step 3: Commit**
```bash
git add mobile/app mobile/src/components
git commit -m "feat(mobile): chat screen with conversations and citations"
```

---

## Task 6: EAS build config + docs + final pass

**Files:**
- Create/modify: `mobile/eas.json` (dev build profile), `mobile/README.md`
- Modify: root `README.md` (mention the mobile app)

- [x] **Step 1: EAS config** — Run `cd mobile && npx eas build:configure` (or hand-write `eas.json` per the installed EAS docs) with at least a `development` profile that builds a dev client. Document that the Google native module requires a dev/EAS build, not Expo Go.

- [x] **Step 2: `mobile/README.md`** — Document: required `extra` config (`apiBase` as the machine's LAN IP, `googleWebClientId`, `googleIosClientId`); that `googleWebClientId` must be in the backend `GOOGLE_CLIENT_IDS`; iOS/Android OAuth client setup + reversed-client-id URL scheme; how to run a dev build; and that the user's email must be on the backend allowlist (bootstrap admin or admin-added) to sign in.

- [x] **Step 3: Final pass** — `cd mobile && pnpm test && npx tsc --noEmit && npx expo lint` (if the template includes a lint script). All clean. Walk the full flow on a dev build: sign in → upload → chat with citation → sign out → relaunch (still requires sign-in after sign-out).

- [x] **Step 4: Commit**
```bash
git add mobile/eas.json mobile/README.md README.md
git commit -m "feat(mobile): EAS dev build config and docs"
```

---

## Self-Review (completed during planning)

**Spec coverage:** Expo + expo-router app (Task 1); secure-store token + authenticated API client (Task 2, unit-tested); native Google sign-in → backend JWT with the gate (Task 3); document upload/list/delete (Task 4); chat with server conversations + citations (Task 5); EAS dev build + docs (Task 6). Admin is intentionally web-only (out of scope for mobile, per the foundation decisions).

**Version-risk handling:** every native/Expo touch-point (`create-expo-app` template, `expo install` version selection, the google-signin `signIn()` result shape, `expo-document-picker` result shape, `expo-router` guard pattern, EAS config) carries an explicit "consult the installed package docs" instruction. The framework-agnostic logic (config, token store, API client, the auth flow sequence) is concrete and unit-tested with jest-expo by mocking `expo-secure-store`, `expo-constants`, and `fetch`.

**Type/name consistency:** `auth-storage.{saveToken,loadToken,clearToken}`, `api.{googleLogin,me,listDocuments,deleteDocument,query,uploadDocument}`, `UnauthorizedError`, `useAuth()` → `{user, ready, signIn, signOut}`, and the shared types match the backend contract and the web app's equivalents. `query(text, conversationId)` → `{text, conversation_id}`.

**Known constraints (flagged, not hidden):**
- The Google native module cannot run in Expo Go — a dev/EAS build is required, so Task 3+ verification needs a simulator or device. If the execution environment can't produce a device build, those tasks must be verified by a human on a real build; the unit tests cover only the logic layer.
- `@react-native-google-signin`'s `signIn()` return shape and `expo-document-picker`'s result shape have BOTH changed across SDK versions — the plan calls these out as must-verify rather than assuming.
- On a physical device, `apiBase` must be the machine's LAN IP (or a tunnel), not `localhost`.
