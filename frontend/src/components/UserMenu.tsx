"use client";

import { useAuth } from "@/lib/auth-context";

export function UserMenu() {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-zinc-500 dark:text-zinc-400 hidden sm:inline">
        {user.email}
      </span>
      <button
        type="button"
        onClick={logout}
        className="px-3 py-1.5 rounded-md text-sm hover:bg-zinc-100 dark:hover:bg-zinc-900 transition-colors"
      >
        Sign out
      </button>
    </div>
  );
}
