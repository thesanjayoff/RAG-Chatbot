import { useEffect, useState } from "react";
import * as api from "../../lib/api";
import type { Citation, DocumentRecord } from "../../lib/types";
import { renderMessageContent } from "../../lib/renderMessageContent";
import { useViewerStore } from "../../store/useViewerStore";
import Modal from "../common/Modal";
import Spinner from "../common/Spinner";

function openCitation(c: Citation) {
  useViewerStore.getState().open({
    documentId: c.document_id,
    filename: c.filename,
    fileType: c.filename.toLowerCase().endsWith(".pdf") ? "pdf" : "other",
    page: c.page_start,
    highlightText: c.snippet,
  });
}

export default function SummarizeModal({ documents, onClose }: { documents: DocumentRecord[]; onClose: () => void }) {
  const [summary, setSummary] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .summarizeDocuments(documents.map((d) => d.id))
      .then((res) => {
        if (cancelled) return;
        setSummary(res.summary);
        setCitations(res.citations);
      })
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : String(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [documents]);

  return (
    <Modal title={`Summary of ${documents.length} document${documents.length === 1 ? "" : "s"}`} onClose={onClose} width="max-w-2xl">
      <p className="mb-3 text-xs text-ink-muted">{documents.map((d) => d.filename).join(", ")}</p>
      {loading && (
        <div className="flex items-center gap-2 py-8 text-sm text-ink-muted">
          <Spinner /> Summarizing...
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {!loading && !error && <div className="text-sm text-ink">{renderMessageContent(summary, citations, openCitation)}</div>}
    </Modal>
  );
}
