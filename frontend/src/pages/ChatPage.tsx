import { useEffect, useRef } from "react";
import { Download, MessageSquare } from "lucide-react";
import { useChatStore } from "../store/useChatStore";
import MessageBubble from "../components/chat/MessageBubble";
import MessageInput from "../components/chat/MessageInput";
import EmptyState from "../components/common/EmptyState";
import { exportConversationUrl } from "../lib/api";

const SUGGESTIONS = [
  "Summarize the key points of this document",
  "What numbers or figures are mentioned?",
  "Is there anything about dates or deadlines?",
  "What differs between my two most recent documents?",
];

export default function ChatPage() {
  const { messages, activeConversationId, sendMessage } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex h-full flex-1 flex-col">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-ink">
          <MessageSquare size={16} className="text-brand" />
          Chat with your documents
        </div>
        {activeConversationId && messages.length > 0 && (
          <div className="flex gap-1.5">
            <a
              href={exportConversationUrl(activeConversationId, "markdown")}
              className="rounded-lg px-2.5 py-1.5 text-xs text-ink-muted hover:bg-surface-muted hover:text-ink cursor-pointer"
              download
            >
              <Download size={13} className="mr-1 inline" /> Markdown
            </a>
            <a
              href={exportConversationUrl(activeConversationId, "pdf")}
              className="rounded-lg px-2.5 py-1.5 text-xs text-ink-muted hover:bg-surface-muted hover:text-ink cursor-pointer"
              download
            >
              <Download size={13} className="mr-1 inline" /> PDF
            </a>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-5">
        {messages.length === 0 ? (
          <EmptyState
            icon={<MessageSquare size={32} />}
            title="Ask anything about your documents"
            description="Answers are grounded only in what you've uploaded, with clickable citations back to the exact page and passage."
            action={
              <div className="mt-2 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => sendMessage(s)}
                    className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-ink-muted hover:text-ink cursor-pointer"
                  >
                    {s}
                  </button>
                ))}
              </div>
            }
          />
        ) : (
          <div className="mx-auto max-w-3xl space-y-5">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="mx-auto w-full max-w-3xl">
        <MessageInput />
      </div>
    </div>
  );
}
