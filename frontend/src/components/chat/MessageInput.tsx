import { useEffect, useRef, useState } from "react";
import { Square, ArrowUp } from "lucide-react";
import { useChatStore } from "../../store/useChatStore";
import FilterBar from "./FilterBar";

export default function MessageInput() {
  const { sendMessage, isStreaming, stopStreaming } = useChatStore();
  const [text, setText] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [text]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "n") {
        e.preventDefault();
        useChatStore.getState().newConversation();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        document.getElementById("conversation-search-input")?.focus();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "/") {
        e.preventDefault();
        taRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = () => {
    if (!text.trim() || isStreaming) return;
    sendMessage(text);
    setText("");
  };

  return (
    <div className="border-t border-border bg-surface px-4 py-3">
      <div className="mb-2">
        <FilterBar />
      </div>
      <div className="flex items-end gap-2 rounded-2xl border border-border bg-canvas px-3 py-2 focus-within:ring-2 focus-within:ring-brand/40">
        <textarea
          ref={taRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder="Ask a question about your documents... (Ctrl+/ to focus, Shift+Enter for newline)"
          className="max-h-48 flex-1 resize-none bg-transparent text-sm text-ink placeholder:text-ink-muted focus:outline-none"
        />
        {isStreaming ? (
          <button
            onClick={stopStreaming}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-canvas cursor-pointer"
            title="Stop generating"
          >
            <Square size={13} />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!text.trim()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand text-white disabled:opacity-30 cursor-pointer"
            title="Send"
          >
            <ArrowUp size={16} />
          </button>
        )}
      </div>
      <p className="mt-1.5 px-1 text-[11px] text-ink-muted">
        Answers are grounded only in your documents, with citations. Document content is treated as data, never as instructions.
      </p>
    </div>
  );
}
