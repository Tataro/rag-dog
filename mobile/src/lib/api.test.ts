const store: Record<string, string> = {};
jest.mock("expo-secure-store", () => ({
  setItemAsync: jest.fn(async (k: string, v: string) => { store[k] = v; }),
  getItemAsync: jest.fn(async (k: string) => store[k] ?? null),
  deleteItemAsync: jest.fn(async (k: string) => { delete store[k]; }),
}));
jest.mock("expo-constants", () => ({ expoConfig: { extra: { apiBase: "http://test" } } }));

// eslint-disable-next-line import/first
import { api, UnauthorizedError } from "./api";
// eslint-disable-next-line import/first
import { saveToken } from "./auth-storage";

beforeEach(() => { for (const k of Object.keys(store)) delete store[k]; });
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
