"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { api } from "@/lib/api";
import type { DocumentOut } from "@/lib/types";

interface Props {
  onUploaded: (doc: DocumentOut) => void;
}

export function DocumentUploader({ onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        const doc = await api.uploadDocument(file);
        onUploaded(doc);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "upload failed");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="border-2 border-dashed border-zinc-200 dark:border-zinc-800 rounded-xl p-6 text-center bg-zinc-50/50 dark:bg-zinc-900/30">
      <Upload className="mx-auto mb-2 text-zinc-400" size={28} />
      <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-3">
        PDF · Markdown · TXT · DOCX
      </p>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.md,.markdown,.txt,.docx"
        multiple
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 text-sm font-medium hover:opacity-90 disabled:opacity-50"
      >
        {busy ? "Uploading…" : "Choose files"}
      </button>
      {error && (
        <p className="mt-3 text-sm text-rose-600 dark:text-rose-400">{error}</p>
      )}
    </div>
  );
}
