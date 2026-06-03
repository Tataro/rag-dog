"use client";

import { useState } from "react";
import { ChatSidebar } from "@/components/ChatSidebar";
import { ChatThread } from "@/components/ChatThread";

export default function ChatPage() {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  function handleConversationChange(id: string) {
    setActiveConversationId(id);
    // Bump so the sidebar refetches — a brand-new conversation then appears + highlights.
    setReloadKey((k) => k + 1);
  }

  return (
    <div className="flex-1 flex w-full min-h-0">
      <ChatSidebar
        activeId={activeConversationId}
        reloadKey={reloadKey}
        onSelect={setActiveConversationId}
      />
      <div className="flex-1 flex flex-col max-w-3xl mx-auto w-full min-h-0">
        <ChatThread
          conversationId={activeConversationId}
          onConversationChange={handleConversationChange}
        />
      </div>
    </div>
  );
}
