"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, UnauthorizedError } from "./api";
import { clearAuth, loadToken, loadUser, saveAuth } from "./auth-storage";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  ready: boolean;
  loginWithGoogle: (idToken: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const pending = loadUser() && loadToken()
      ? api.me().then(setUser).catch((e) => {
          if (e instanceof UnauthorizedError) {
            clearAuth();
            setUser(null);
          } else {
            // Transient backend error (network/5xx): keep the cached user rather
            // than forcing a spurious sign-out; the token is still valid.
            setUser(loadUser());
          }
        })
      : Promise.resolve();
    pending.finally(() => setReady(true));
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
