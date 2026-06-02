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
