import { useState } from "react";
import * as api from "../../lib/api";
import type { Citation, DocumentRecord } from "../../lib/types";
import { renderMessageContent } from "../../lib/renderMessageContent";
import { useViewerStore } from "../../store/useViewerStore";
import Modal from "../common/Modal";
import Spinner from "../common/Spinner";
import Button from "../common/Button";

function openCitation(c: Citation) {
  useViewerStore.getState().open({
    documentId: c.document_id,
    filename: c.filename,
    fileType: c.filename.toLowerCase().endsWith(".pdf") ? "pdf" : "other",
    page: c.page_start,
    highlightText: c.snippet,
  });
}

export default function CompareModal({ documents, onClose }: { documents: DocumentRecord[]; onClose: () => void }) {
  const mid = Math.ceil(documents.length / 2);
  const [groupA, setGroupA] = useState<string[]>(documents.slice(0, mid).map((d) => d.id));
  const [aspect, setAspect] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const groupB = documents.filter((d) => !groupA.includes(d.id)).map((d) => d.id);

  const toggle = (id: string) => {
    setGroupA((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const run = async () => {
    if (groupA.length === 0 || groupB.length === 0) {
      setError("Put at least one document in each group.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.compareDocuments(groupA, groupB, aspect || undefined);
      setResult(res.comparison);
      setCitations(res.citations);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="Compare documents" onClose={onClose} width="max-w-2xl">
      {!result && (
        <>
          <p className="mb-3 text-xs text-ink-muted">Assign each document to group A or B, then compare.</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="mb-1.5 text-xs font-semibold text-ink-muted">Document A</p>
              <div className="space-y-1">
                {documents.map((d) => (
                  <label key={d.id} className="flex items-center gap-2 rounded-lg px-2 py-1 text-xs text-ink hover:bg-surface-muted cursor-pointer">
                    <input type="checkbox" checked={groupA.includes(d.id)} onChange={() => toggle(d.id)} />
                    <span className="truncate">{d.filename}</span>
                  </label>
                ))}
              </div>
            </div>
            <div>
              <p className="mb-1.5 text-xs font-semibold text-ink-muted">Document B</p>
              <div className="space-y-1">
                {documents.map((d) => (
                  <label key={d.id} className="flex items-center gap-2 rounded-lg px-2 py-1 text-xs text-ink hover:bg-surface-muted cursor-pointer">
                    <input type="checkbox" checked={!groupA.includes(d.id)} onChange={() => toggle(d.id)} />
                    <span className="truncate">{d.filename}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <input
            value={aspect}
            onChange={(e) => setAspect(e.target.value)}
            placeholder="Optional: what should we compare? (default: everything)"
            className="mt-3 w-full rounded-lg border border-border bg-canvas px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand/40"
          />
          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
          <Button variant="primary" className="mt-3" onClick={run} disabled={loading}>
            {loading ? <Spinner size={14} /> : null} Compare
          </Button>
        </>
      )}
      {result && <div className="text-sm text-ink">{renderMessageContent(result, citations, openCitation)}</div>}
    </Modal>
  );
}
