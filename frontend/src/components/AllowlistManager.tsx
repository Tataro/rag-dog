"use client";

import { useCallback, useEffect, useState } from "react";
import { api, UnauthorizedError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { AllowedEmail } from "@/lib/types";

export function AllowlistManager() {
  const { user, logout } = useAuth();
  const [emails, setEmails] = useState<AllowedEmail[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await api.listAllowlist();
      setEmails(list);
      setLoadError(null);
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        logout();
        return;
      }
      setLoadError(e instanceof Error ? e.message : "could not load allowlist");
    }
  }, [logout]);

  useEffect(() => {
    // Only the admin path hits the admin API; a non-admin would just get a 403.
    // setState happens after the awaited fetch resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (user?.is_admin) void load();
  }, [load, user?.is_admin]);

  // UX-only guard. Real authorization is enforced by the backend (403 on every
  // /api/admin/* call); hiding this screen is not a security boundary.
  if (!user?.is_admin) {
    return (
      <p className="text-sm text-zinc-500 italic text-center py-8">
        Not authorized.
      </p>
    );
  }

  async function handleRemove(email: string) {
    setRemoving((prev) => new Set(prev).add(email));
    try {
      await api.removeAllowedEmail(email);
      await load();
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        logout();
        return;
      }
      setLoadError(e instanceof Error ? e.message : "could not remove email");
    } finally {
      setRemoving((prev) => {
        const next = new Set(prev);
        next.delete(email);
        return next;
      });
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!newEmail.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      await api.addAllowedEmail(newEmail.trim());
      setNewEmail("");
      await load();
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        logout();
        return;
      }
      setAddError(err instanceof Error ? err.message : "could not add email");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={handleAdd} className="flex gap-2">
        <input
          type="email"
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          placeholder="user@example.com"
          className="flex-1 px-3 py-1.5 rounded-md border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
          disabled={adding}
        />
        <button
          type="submit"
          disabled={adding || !newEmail.trim()}
          className="px-4 py-1.5 rounded-md text-sm bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 hover:bg-zinc-700 dark:hover:bg-zinc-300 disabled:opacity-50 transition-colors"
        >
          {adding ? "Adding…" : "Add"}
        </button>
      </form>

      {addError && (
        <p className="text-sm text-rose-600 dark:text-rose-400">{addError}</p>
      )}

      {loadError && (
        <p className="text-sm text-rose-600 dark:text-rose-400">{loadError}</p>
      )}

      {emails.length === 0 ? (
        <p className="text-sm text-zinc-500 italic text-center py-8">
          Allowlist is empty. Add an email above.
        </p>
      ) : (
        <ul className="divide-y divide-zinc-200 dark:divide-zinc-800 rounded-xl border border-zinc-200 dark:border-zinc-800">
          {emails.map((entry) => (
            <li
              key={entry.email}
              className="px-4 py-3 flex items-center gap-3 text-sm"
            >
              <span className="flex-1 font-medium truncate">{entry.email}</span>
              <span className="text-xs text-zinc-500 hidden sm:inline">
                added {new Date(entry.created_at).toLocaleDateString()}
              </span>
              <button
                type="button"
                onClick={() => handleRemove(entry.email)}
                disabled={removing.has(entry.email)}
                className="px-2.5 py-1 rounded-md text-sm text-zinc-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/50 disabled:opacity-50 transition-colors"
              >
                {removing.has(entry.email) ? "…" : "Remove"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
