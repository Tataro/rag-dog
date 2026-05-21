"use client";

import { Trash2 } from "lucide-react";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { formatBytes, formatRelative } from "@/lib/format";
import type { DocumentOut } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  docs: DocumentOut[];
  onChanged: () => void;
}

export function DocumentList({ docs, onChanged }: Props) {
  // Poll for status updates while anything is in flight.
  useEffect(() => {
    const pending = docs.some(
      (d) => d.status === "uploading" || d.status === "processing"
    );
    if (!pending) return;
    const t = setInterval(onChanged, 2000);
    return () => clearInterval(t);
  }, [docs, onChanged]);

  if (docs.length === 0) {
    return (
      <p className="text-sm text-zinc-500 italic text-center py-8">
        No documents yet. Upload something to get started.
      </p>
    );
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this document and all its chunks?")) return;
    await api.deleteDocument(id);
    onChanged();
  }

  return (
    <ul className="divide-y divide-zinc-200 dark:divide-zinc-800 rounded-xl border border-zinc-200 dark:border-zinc-800">
      {docs.map((d) => (
        <li
          key={d.id}
          className="px-4 py-3 flex items-center gap-3 text-sm"
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium truncate">{d.filename}</span>
              <StatusBadge status={d.status} />
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">
              {formatBytes(d.size_bytes)}
              {d.page_count !== null && ` · ${d.page_count} pages`}
              {" · "}
              uploaded {formatRelative(d.created_at)}
            </div>
            {d.status === "failed" && d.error && (
              <div className="text-xs text-rose-600 dark:text-rose-400 mt-1 font-mono">
                {d.error}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => handleDelete(d.id)}
            className="p-1.5 rounded-md text-zinc-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/50 transition-colors"
            title="Delete"
          >
            <Trash2 size={16} />
          </button>
        </li>
      ))}
    </ul>
  );
}
