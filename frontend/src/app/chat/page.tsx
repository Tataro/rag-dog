import { ChatThread } from "@/components/ChatThread";

export default function ChatPage() {
  return (
    <div className="flex-1 flex flex-col max-w-3xl mx-auto w-full">
      <ChatThread />
    </div>
  );
}
