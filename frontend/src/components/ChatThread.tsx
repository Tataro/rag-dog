"use client";

import { useEffect, useRef, useState } from "react";
import { RotateCcw, Send } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { api, UnauthorizedError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { ChatTurn } from "@/lib/types";
import { CitationCard } from "./CitationCard";

export function ChatThread() {
  const { logout } = useAuth();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

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
      setConversationId(res.conversation_id);
      setTurns([
        ...next,
        { role: "assistant", content: res.answer, citations: res.citations },
      ]);
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

  function handleReset() {
    if (turns.length > 0 && !confirm("Start a new conversation?")) return;
    setConversationId(null);
    setTurns([]);
    setError(null);
  }

  return (
    <div className="flex flex-col h-full">
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
        {error && (
          <div className="text-sm text-rose-600 dark:text-rose-400">{error}</div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSend}
        className="border-t border-zinc-200 dark:border-zinc-800 px-4 py-3 flex items-end gap-2 bg-white dark:bg-zinc-950"
      >
        <button
          type="button"
          onClick={handleReset}
          className="p-2 rounded-md text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
          title="New conversation"
        >
          <RotateCcw size={18} />
        </button>
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
