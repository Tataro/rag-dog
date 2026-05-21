import { FileText } from "lucide-react";
import type { Citation } from "@/lib/types";

export function CitationCard({ citation }: { citation: Citation }) {
  const where: string[] = [];
  if (citation.page !== null) where.push(`p.${citation.page}`);
  if (citation.section) where.push(`§ ${citation.section}`);

  return (
    <div className="border border-zinc-200 dark:border-zinc-800 rounded-lg p-3 bg-zinc-50/60 dark:bg-zinc-900/40 text-sm">
      <div className="flex items-center gap-2 mb-1">
        <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 text-xs font-semibold">
          {citation.marker}
        </span>
        <FileText size={14} className="text-zinc-500" />
        <span className="font-medium truncate">{citation.filename}</span>
        {where.length > 0 && (
          <span className="text-xs text-zinc-500">· {where.join(" · ")}</span>
        )}
      </div>
      <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
        {citation.snippet}
      </p>
    </div>
  );
}
