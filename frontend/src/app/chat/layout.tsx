"use client";

import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { ChatSidebar } from "@/components/ChatSidebar";
import { ChatThread } from "@/components/ChatThread";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  // The selected conversation lives in the path (`/chat/<id>`), so it's deep-linkable
  // and the browser back/forward buttons move between conversations.
  const match = pathname.match(/^\/chat\/(.+)$/);
  const activeConversationId = match ? decodeURIComponent(match[1]) : null;
  const [reloadKey, setReloadKey] = useState(0);

  function select(id: string | null) {
    router.push(id ? `/chat/${id}` : "/chat");
  }

  function handleConversationChange(id: string) {
    // After a send: navigate only for a brand-new conversation (continuations are
    // already on this path), but always refresh the sidebar so ordering/new rows update.
    if (id !== activeConversationId) router.push(`/chat/${id}`);
    setReloadKey((k) => k + 1);
  }

  return (
    <div className="flex-1 flex w-full min-h-0">
      <ChatSidebar activeId={activeConversationId} reloadKey={reloadKey} onSelect={select} />
      <div className="flex-1 flex flex-col max-w-3xl mx-auto w-full min-h-0">
        <ChatThread
          conversationId={activeConversationId}
          onConversationChange={handleConversationChange}
        />
      </div>
      {/* Pages under /chat are route markers (they render null). The workspace lives here
          in the layout so the sidebar + thread persist across conversation navigations
          (no remount → no refetch/flicker when a new conversation changes the path). */}
      {children}
    </div>
  );
}
