import { useState } from "react";
import { AlertCircle, ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import type { ChatMessage, Citation } from "../../lib/types";
import { renderMessageContent } from "../../lib/renderMessageContent";
import { useViewerStore } from "../../store/useViewerStore";
import Badge from "../common/Badge";

function openCitation(c: Citation) {
  useViewerStore.getState().open({
    documentId: c.document_id,
    filename: c.filename,
    fileType: c.filename.toLowerCase().endsWith(".pdf") ? "pdf" : "other",
    page: c.page_start,
    highlightText: c.snippet,
  });
}

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const [chunksOpen, setChunksOpen] = useState(false);
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-brand px-4 py-2.5 text-sm text-white whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  const isEmpty = !message.content && message.streaming;

  return (
    <div className="flex justify-start gap-3 animate-fade-in">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
        <Sparkles size={14} />
      </div>
      <div className="max-w-[80%] flex-1">
        <div className="rounded-2xl rounded-tl-sm bg-surface-muted px-4 py-2.5 text-sm text-ink">
          {isEmpty ? (
            <span className="inline-flex gap-1">
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-ink-muted" />
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-ink-muted" style={{ animationDelay: "0.15s" }} />
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-ink-muted" style={{ animationDelay: "0.3s" }} />
            </span>
          ) : (
            <div>{renderMessageContent(message.content, message.citations ?? undefined, openCitation)}</div>
          )}

          {message.not_found && !message.streaming && (
            <div className="mt-2 flex items-center gap-1.5 text-xs text-ink-muted">
              <AlertCircle size={13} />
              Not found in your documents.
            </div>
          )}
          {message.used_general_knowledge && (
            <Badge tone="warning" className="mt-2">
              Includes general knowledge beyond your documents
            </Badge>
          )}
        </div>

        {message.retrieved && message.retrieved.length > 0 && (
          <div className="mt-1.5">
            <button
              onClick={() => setChunksOpen((v) => !v)}
              className="flex items-center gap-1 text-xs text-ink-muted hover:text-ink cursor-pointer"
            >
              {chunksOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              {chunksOpen ? "Hide" : "Show"} {message.retrieved.length} retrieved passage{message.retrieved.length === 1 ? "" : "s"}
            </button>
            {chunksOpen && (
              <div className="mt-2 space-y-2">
                {message.retrieved.map((r) => (
                  <div key={r.chunk_id} className="rounded-lg border border-border bg-surface px-3 py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-ink">
                        {r.filename}
                        {r.page_start ? ` — p.${r.page_start}` : ""}
                      </span>
                      <span className="shrink-0 text-ink-muted">
                        {r.rerank_score !== null ? `score ${r.rerank_score.toFixed(2)}` : `fused ${r.fused_score.toFixed(2)}`}
                      </span>
                    </div>
                    {r.text && <p className="mt-1 line-clamp-3 text-ink-muted">{r.text}</p>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
