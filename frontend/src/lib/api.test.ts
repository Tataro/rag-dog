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
