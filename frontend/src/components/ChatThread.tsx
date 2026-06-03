"use client";

import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { api, UnauthorizedError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { ChatTurn } from "@/lib/types";
import { CitationCard } from "./CitationCard";

export function ChatThread({
  conversationId,
  onConversationChange,
}: {
  conversationId: string | null;
  onConversationChange: (id: string) => void;
}) {
  const { logout } = useAuth();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // The conversation currently shown in `turns`. Lets us skip a redundant refetch
  // after a send (which bumps `conversationId` to a value we already have loaded).
  const loadedIdRef = useRef<string | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  // Load (or clear) the thread when the selected conversation changes.
  useEffect(() => {
    if (conversationId === loadedIdRef.current) return;

    let cancelled = false;

    (async () => {
      if (conversationId === null) {
        loadedIdRef.current = null;
        if (!cancelled) {
          setTurns([]);
          setError(null);
        }
        return;
      }

      try {
        const convo = await api.getConversation(conversationId);
        if (cancelled) return;
        loadedIdRef.current = conversationId;
        setTurns(
          convo.messages.map((m) => ({
            role: m.role,
            content: m.content,
            citations: m.citations ?? undefined,
          })),
        );
        setError(null);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UnauthorizedError) {
          logout();
          return;
        }
        setError(err instanceof Error ? err.message : "failed to load conversation");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [conversationId, logout]);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    setBusy(true);
    setError(null);
    setInput("");
    const next = [...turns, { role: "user", content: text } as ChatTurn];
    setTurns(next);

    try {
      const res = await api.query(text, conversationId);
      loadedIdRef.current = res.conversation_id; // we already hold this conversation's turns
      setTurns([...next, { role: "assistant", content: res.answer, citations: res.citations }]);
      onConversationChange(res.conversation_id);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        logout();
        return;
      }
      setError(err instanceof Error ? err.message : "query failed");
      setTurns(next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        {turns.length === 0 && (
          <div className="text-center text-zinc-500 italic text-sm mt-12">
            Ask anything about your uploaded documents.
          </div>
        )}
        {turns.map((t, i) => (
          <Turn key={i} turn={t} />
        ))}
        {busy && (
          <div className="text-sm text-zinc-500 italic flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-zinc-400 animate-pulse" />
            thinking…
          </div>
        )}
        {error && <div className="text-sm text-rose-600 dark:text-rose-400">{error}</div>}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSend}
        className="border-t border-zinc-200 dark:border-zinc-800 px-4 py-3 flex items-end gap-2 bg-white dark:bg-zinc-950"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSend(e as unknown as React.FormEvent);
            }
          }}
          rows={1}
          placeholder="Ask a question…"
          className="flex-1 resize-none rounded-md border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:focus:ring-zinc-100/10"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="p-2 rounded-md bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 disabled:opacity-40"
          title="Send"
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}

function Turn({ turn }: { turn: ChatTurn }) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 px-4 py-2 text-sm whitespace-pre-wrap">
          {turn.content}
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed">
        <ReactMarkdown>{turn.content}</ReactMarkdown>
      </div>
      {turn.citations && turn.citations.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {turn.citations.map((c) => (
            <CitationCard key={c.chunk_id} citation={c} />
          ))}
        </div>
      )}
    </div>
  );
}
