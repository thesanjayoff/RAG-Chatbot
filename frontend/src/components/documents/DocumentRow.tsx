import { useState } from "react";
import { AlertTriangle, Eye, FileText, KeyRound, RefreshCw, ScanText, Tag as TagIcon, Trash2 } from "lucide-react";
import type { DocumentRecord } from "../../lib/types";
import { useDocumentsStore } from "../../store/useDocumentsStore";
import { useViewerStore } from "../../store/useViewerStore";
import Badge from "../common/Badge";
import Spinner from "../common/Spinner";

const STATUS_TONE: Record<string, "neutral" | "brand" | "warning" | "danger" | "success"> = {
  pending: "neutral",
  processing: "brand",
  ready: "success",
  error: "danger",
  skipped: "neutral",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentRow({
  doc,
  selected,
  onToggleSelect,
}: {
  doc: DocumentRecord;
  selected: boolean;
  onToggleSelect: () => void;
}) {
  const { remove, reindex, setTags } = useDocumentsStore();
  const [editingTags, setEditingTags] = useState(false);
  const [tagInput, setTagInput] = useState(doc.tags.join(", "));

  const openViewer = () => {
    useViewerStore.getState().open({ documentId: doc.id, filename: doc.filename, fileType: doc.file_type, page: 1 });
  };

  const saveTags = async () => {
    const tags = tagInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    await setTags(doc.id, tags);
    setEditingTags(false);
  };

  return (
    <div className="flex items-start gap-3 rounded-xl border border-border bg-surface px-4 py-3">
      <input type="checkbox" checked={selected} onChange={onToggleSelect} className="mt-1.5 cursor-pointer" />
      <div className="mt-0.5 text-ink-muted">
        <FileText size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <button onClick={openViewer} className="truncate text-sm font-medium text-ink hover:underline cursor-pointer" title={doc.filename}>
            {doc.filename}
          </button>
          <Badge tone={STATUS_TONE[doc.status]}>{doc.status}</Badge>
          {doc.used_ocr && (
            <span title="Text recovered via OCR">
              <Badge tone="brand">
                <ScanText size={11} /> OCR
              </Badge>
            </span>
          )}
          {doc.secrets_flag && (
            <span title={doc.secrets_summary ?? "Possible secrets/PII detected"}>
              <Badge tone="warning">
                <KeyRound size={11} /> secrets
              </Badge>
            </span>
          )}
          {doc.injection_flag && (
            <span title={doc.injection_summary ?? "Prompt-injection-style text detected"}>
              <Badge tone="danger">
                <AlertTriangle size={11} /> injection text
              </Badge>
            </span>
          )}
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
          <span>{formatSize(doc.size_bytes)}</span>
          {doc.page_count > 0 && <span>{doc.page_count} pages</span>}
          <span>{doc.chunk_count} chunks</span>
          <span className="uppercase">{doc.file_type}</span>
          {(doc.status === "pending" || doc.status === "processing") && (
            <span className="flex items-center gap-1 text-brand">
              <Spinner size={11} /> {Math.round(doc.progress * 100)}%
            </span>
          )}
        </div>

        {doc.status === "error" && doc.error_message && <p className="mt-1 text-xs text-red-600">{doc.error_message}</p>}

        {editingTags ? (
          <div className="mt-2 flex items-center gap-1.5">
            <input
              autoFocus
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveTags()}
              placeholder="tag1, tag2"
              className="rounded-md border border-border bg-canvas px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-brand/40"
            />
            <button onClick={saveTags} className="text-xs text-brand cursor-pointer">
              Save
            </button>
            <button onClick={() => setEditingTags(false)} className="text-xs text-ink-muted cursor-pointer">
              Cancel
            </button>
          </div>
        ) : (
          <div className="mt-1.5 flex flex-wrap items-center gap-1">
            {doc.tags.map((t) => (
              <Badge key={t} tone="neutral">
                #{t}
              </Badge>
            ))}
            <button onClick={() => setEditingTags(true)} className="flex items-center gap-1 text-xs text-ink-muted hover:text-ink cursor-pointer">
              <TagIcon size={11} /> {doc.tags.length === 0 ? "Add tags" : "Edit"}
            </button>
          </div>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <button onClick={openViewer} title="Preview" className="rounded-lg p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink cursor-pointer">
          <Eye size={15} />
        </button>
        <button onClick={() => reindex(doc.id)} title="Re-index" className="rounded-lg p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink cursor-pointer">
          <RefreshCw size={15} />
        </button>
        <button
          onClick={() => confirm(`Delete "${doc.filename}"? This removes it from the library and search index.`) && remove(doc.id)}
          title="Delete"
          className="rounded-lg p-1.5 text-ink-muted hover:bg-red-50 hover:text-red-600 cursor-pointer dark:hover:bg-red-900/30"
        >
          <Trash2 size={15} />
        </button>
      </div>
    </div>
  );
}
