"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { api, UnauthorizedError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatRelative } from "@/lib/format";
import type { ConversationOut } from "@/lib/types";

export function ChatSidebar({
  activeId,
  reloadKey,
  onSelect,
}: {
  activeId: string | null;
  reloadKey: number;
  onSelect: (id: string | null) => void;
}) {
  const { logout } = useAuth();
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await api.listConversations();
        if (!cancelled) {
          setConversations(list);
          setError(null);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UnauthorizedError) {
          logout();
          return;
        }
        setError(err instanceof Error ? err.message : "failed to load history");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, logout]);

  return (
    <aside className="hidden md:flex md:flex-col w-64 shrink-0 border-r border-zinc-200 dark:border-zinc-800 overflow-y-auto">
      <div className="p-3">
        <button
          type="button"
          onClick={() => onSelect(null)}
          className="w-full inline-flex items-center justify-center gap-2 rounded-md border border-zinc-200 dark:border-zinc-800 px-3 py-2 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-900"
        >
          <Plus size={16} />
          New chat
        </button>
      </div>
      {error && <div className="px-3 py-2 text-xs text-rose-600 dark:text-rose-400">{error}</div>}
      <nav className="flex-1 px-2 pb-3 space-y-1">
        {conversations.length === 0 && !error && (
          <p className="px-2 py-4 text-xs text-zinc-500 italic">No conversations yet.</p>
        )}
        {conversations.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => onSelect(c.id)}
            className={`w-full text-left rounded-md px-2 py-2 text-sm transition-colors ${
              c.id === activeId
                ? "bg-zinc-100 dark:bg-zinc-900"
                : "hover:bg-zinc-100/60 dark:hover:bg-zinc-900/60"
            }`}
          >
            <span className="block truncate">{c.preview || "Untitled"}</span>
            <span className="block text-xs text-zinc-500">{formatRelative(c.last_message_at)}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}
