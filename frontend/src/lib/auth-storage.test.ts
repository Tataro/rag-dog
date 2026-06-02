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
