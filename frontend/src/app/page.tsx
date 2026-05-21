import Link from "next/link";
import { MessageSquare, FileText } from "lucide-react";

export default function HomePage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-16 w-full">
      <h1 className="text-3xl font-semibold tracking-tight mb-2">🐶 rag-dog</h1>
      <p className="text-zinc-600 dark:text-zinc-400 mb-8 max-w-prose">
        A local, single-user RAG over your own documents. Everything runs on
        your machine — no documents leave it, no API keys, no cloud LLM.
      </p>

      <div className="grid sm:grid-cols-2 gap-4">
        <HomeCard
          href="/documents"
          icon={<FileText size={22} />}
          title="Documents"
          description="Upload PDFs, Markdown, TXT, DOCX. Watch them get indexed."
        />
        <HomeCard
          href="/chat"
          icon={<MessageSquare size={22} />}
          title="Chat"
          description="Ask questions; answers come with source citations."
        />
      </div>

      <p className="text-xs text-zinc-500 mt-12">
        Models: bge-m3 for embeddings, qwen2.5:14b-instruct for generation —
        both via Ollama.
      </p>
    </div>
  );
}

function HomeCard({
  href,
  icon,
  title,
  description,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="block p-5 rounded-xl border border-zinc-200 dark:border-zinc-800 hover:border-zinc-400 dark:hover:border-zinc-600 transition-colors"
    >
      <div className="flex items-center gap-3 mb-2 text-zinc-700 dark:text-zinc-300">
        {icon}
        <span className="font-semibold">{title}</span>
      </div>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">{description}</p>
    </Link>
  );
}
