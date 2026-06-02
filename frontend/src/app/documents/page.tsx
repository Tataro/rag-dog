"use client";

import { useCallback, useEffect, useState } from "react";
import { api, UnauthorizedError } from "@/lib/api";
import { DocumentList } from "@/components/DocumentList";
import { DocumentUploader } from "@/components/DocumentUploader";
import { useAuth } from "@/lib/auth-context";
import type { DocumentOut } from "@/lib/types";

export default function DocumentsPage() {
  const { logout } = useAuth();
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.listDocuments();
      setDocs(next);
      setLoadError(null);
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        logout();
        return;
      }
      setLoadError(e instanceof Error ? e.message : "could not load documents");
    }
  }, [logout]);

  useEffect(() => {
    // Initial document load. setState happens after the awaited fetch resolves —
    // the lint rule is conservative about this pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 w-full space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
      <DocumentUploader
        onUploaded={(d) => setDocs((prev) => [d, ...prev])}
      />
      {loadError && (
        <p className="text-sm text-rose-600 dark:text-rose-400">{loadError}</p>
      )}
      <DocumentList docs={docs} onChanged={refresh} />
    </div>
  );
}
