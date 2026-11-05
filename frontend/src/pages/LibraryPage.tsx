import { useEffect, useMemo, useState } from "react";
import { FileStack, Layers, Search } from "lucide-react";
import { useDocumentsStore } from "../store/useDocumentsStore";
import UploadDropzone from "../components/documents/UploadDropzone";
import DocumentRow from "../components/documents/DocumentRow";
import WatchedFoldersPanel from "../components/documents/WatchedFoldersPanel";
import UrlIngestForm from "../components/documents/UrlIngestForm";
import SummarizeModal from "../components/analysis/SummarizeModal";
import CompareModal from "../components/analysis/CompareModal";
import EmptyState from "../components/common/EmptyState";
import Button from "../components/common/Button";

export default function LibraryPage() {
  const { documents, load, startPolling } = useDocumentsStore();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [modal, setModal] = useState<"summarize" | "compare" | null>(null);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (documents.some((d) => d.status === "pending" || d.status === "processing")) {
      startPolling();
    }
  }, [documents, startPolling]);

  const filtered = useMemo(() => {
    if (!query.trim()) return documents;
    const q = query.toLowerCase();
    return documents.filter((d) => d.filename.toLowerCase().includes(q) || d.tags.some((t) => t.toLowerCase().includes(q)));
  }, [documents, query]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectedDocs = documents.filter((d) => selected.has(d.id));

  return (
    <div className="flex h-full flex-1 overflow-hidden">
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-4xl space-y-5">
          <div>
            <h1 className="text-lg font-semibold text-ink">Document library</h1>
            <p className="text-sm text-ink-muted">Upload, tag, preview, and manage the files your chatbot can see.</p>
          </div>

          <UploadDropzone />

          <div className="flex items-center justify-between gap-3">
            <div className="relative flex-1">
              <Search size={14} className="pointer-events-none absolute left-3 top-2.5 text-ink-muted" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by filename or tag..."
                className="w-full rounded-lg border border-border bg-surface py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand/40"
              />
            </div>
            {selected.size > 0 && (
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-xs text-ink-muted">{selected.size} selected</span>
                <Button size="sm" icon={<FileStack size={14} />} onClick={() => setModal("summarize")}>
                  Summarize
                </Button>
                <Button size="sm" icon={<Layers size={14} />} onClick={() => setModal("compare")} disabled={selected.size < 2}>
                  Compare
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
                  Clear
                </Button>
              </div>
            )}
          </div>

          {filtered.length === 0 ? (
            <EmptyState
              icon={<FileStack size={32} />}
              title={documents.length === 0 ? "No documents yet" : "No matches"}
              description={
                documents.length === 0
                  ? "Upload a file above, add a folder to watch, or fetch a web page to get started."
                  : "Try a different search term."
              }
            />
          ) : (
            <div className="space-y-2">
              {filtered.map((d) => (
                <DocumentRow key={d.id} doc={d} selected={selected.has(d.id)} onToggleSelect={() => toggleSelect(d.id)} />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="w-80 shrink-0 space-y-4 overflow-y-auto border-l border-border bg-canvas px-4 py-6">
        <UrlIngestForm />
        <WatchedFoldersPanel />
      </div>

      {modal === "summarize" && <SummarizeModal documents={selectedDocs} onClose={() => setModal(null)} />}
      {modal === "compare" && <CompareModal documents={selectedDocs} onClose={() => setModal(null)} />}
    </div>
  );
}
