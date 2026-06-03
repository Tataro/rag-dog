const store: Record<string, string> = {};
jest.mock("expo-secure-store", () => ({
  setItemAsync: jest.fn(async (k: string, v: string) => { store[k] = v; }),
  getItemAsync: jest.fn(async (k: string) => store[k] ?? null),
  deleteItemAsync: jest.fn(async (k: string) => { delete store[k]; }),
}));

// eslint-disable-next-line import/first
import { clearToken, loadToken, saveToken } from "./auth-storage";

beforeEach(() => { for (const k of Object.keys(store)) delete store[k]; });

test("round-trips the token", async () => {
  expect(await loadToken()).toBeNull();
  await saveToken("jwt-1");
  expect(await loadToken()).toBe("jwt-1");
  await clearToken();
  expect(await loadToken()).toBeNull();
});
