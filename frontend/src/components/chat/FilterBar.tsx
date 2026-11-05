import { useEffect, useRef, useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import { useChatStore } from "../../store/useChatStore";
import { useDocumentsStore } from "../../store/useDocumentsStore";
import Toggle from "../common/Toggle";

export default function FilterBar() {
  const { filters, setFilters, showChunks, setShowChunks, allowGeneralKnowledge, setAllowGeneralKnowledge, useSubquestions, setUseSubquestions } =
    useChatStore();
  const { documents, tags, load } = useDocumentsStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const activeDocIds = filters.document_ids ?? [];
  const activeTags = filters.tag_names ?? [];
  const activeCount = activeDocIds.length + activeTags.length;

  const toggleDoc = (id: string) => {
    const next = activeDocIds.includes(id) ? activeDocIds.filter((d) => d !== id) : [...activeDocIds, id];
    setFilters({ ...filters, document_ids: next.length ? next : null });
  };
  const toggleTag = (name: string) => {
    const next = activeTags.includes(name) ? activeTags.filter((t) => t !== name) : [...activeTags, name];
    setFilters({ ...filters, tag_names: next.length ? next : null });
  };

  return (
    <div className="relative" ref={ref}>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-ink-muted hover:text-ink cursor-pointer"
        >
          <SlidersHorizontal size={13} />
          Filters & options
          {activeCount > 0 && <span className="rounded-full bg-brand px-1.5 text-[10px] text-white">{activeCount}</span>}
        </button>

        {activeDocIds.map((id) => {
          const doc = documents.find((d) => d.id === id);
          return (
            <span key={id} className="flex items-center gap-1 rounded-full bg-surface-muted px-2 py-1 text-xs text-ink">
              {doc?.filename ?? id}
              <button onClick={() => toggleDoc(id)} className="cursor-pointer text-ink-muted hover:text-ink">
                <X size={11} />
              </button>
            </span>
          );
        })}
        {activeTags.map((t) => (
          <span key={t} className="flex items-center gap-1 rounded-full bg-surface-muted px-2 py-1 text-xs text-ink">
            #{t}
            <button onClick={() => toggleTag(t)} className="cursor-pointer text-ink-muted hover:text-ink">
              <X size={11} />
            </button>
          </span>
        ))}
      </div>

      {open && (
        <div className="absolute bottom-full z-20 mb-2 w-80 rounded-xl border border-border bg-surface p-3 shadow-lg animate-fade-in">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">Answer options</p>
          <Toggle checked={showChunks} onChange={setShowChunks} label="Show retrieved passages" description="See exactly what was retrieved" />
          <Toggle
            checked={allowGeneralKnowledge}
            onChange={setAllowGeneralKnowledge}
            label="Allow general knowledge"
            description="Only when your documents don't have the answer"
          />
          <Toggle checked={useSubquestions} onChange={setUseSubquestions} label="Split complex questions" description="Break into sub-questions first" />

          <p className="mb-1.5 mt-3 text-xs font-semibold uppercase tracking-wide text-ink-muted">Restrict to tags</p>
          <div className="flex flex-wrap gap-1.5">
            {tags.length === 0 && <p className="text-xs text-ink-muted">No tags yet.</p>}
            {tags.map((t) => (
              <button
                key={t}
                onClick={() => toggleTag(t)}
                className={`rounded-full px-2 py-1 text-xs cursor-pointer ${
                  activeTags.includes(t) ? "bg-brand text-white" : "bg-surface-muted text-ink-muted hover:text-ink"
                }`}
              >
                #{t}
              </button>
            ))}
          </div>

          <p className="mb-1.5 mt-3 text-xs font-semibold uppercase tracking-wide text-ink-muted">Restrict to files</p>
          <div className="max-h-36 space-y-1 overflow-y-auto">
            {documents.length === 0 && <p className="text-xs text-ink-muted">No documents yet.</p>}
            {documents.map((d) => (
              <label key={d.id} className="flex items-center gap-2 rounded-lg px-1 py-1 text-xs text-ink hover:bg-surface-muted cursor-pointer">
                <input type="checkbox" checked={activeDocIds.includes(d.id)} onChange={() => toggleDoc(d.id)} />
                <span className="truncate">{d.filename}</span>
              </label>
            ))}
          </div>

          {activeCount > 0 && (
            <button
              onClick={() => setFilters({})}
              className="mt-3 w-full rounded-lg border border-border py-1.5 text-xs text-ink-muted hover:text-ink cursor-pointer"
            >
              Clear all filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}
