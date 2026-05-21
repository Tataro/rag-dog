import Link from "next/link";
import { MessageSquare, FileText } from "lucide-react";

export function Nav() {
  return (
    <nav className="border-b border-zinc-200 dark:border-zinc-800 bg-white/70 dark:bg-zinc-950/70 backdrop-blur">
      <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-6">
        <Link href="/" className="font-semibold tracking-tight">
          🐶 rag-dog
        </Link>
        <div className="flex gap-1 ml-auto">
          <NavLink href="/chat" icon={<MessageSquare size={16} />} label="Chat" />
          <NavLink
            href="/documents"
            icon={<FileText size={16} />}
            label="Documents"
          />
        </div>
      </div>
    </nav>
  );
}

function NavLink({
  href,
  icon,
  label,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm hover:bg-zinc-100 dark:hover:bg-zinc-900 transition-colors"
    >
      {icon}
      {label}
    </Link>
  );
}
