import type { DocumentStatus } from "@/lib/types";

const STYLES: Record<DocumentStatus, string> = {
  uploading: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  processing: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  ready: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  failed: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STYLES[status]}`}
    >
      {status}
    </span>
  );
}
