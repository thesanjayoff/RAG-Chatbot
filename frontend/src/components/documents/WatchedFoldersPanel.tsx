import { useEffect, useState } from "react";
import { FolderSync, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useDocumentsStore } from "../../store/useDocumentsStore";
import * as api from "../../lib/api";
import Button from "../common/Button";

export default function WatchedFoldersPanel() {
  const { watchedFolders, loadWatchedFolders } = useDocumentsStore();
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    loadWatchedFolders();
  }, [loadWatchedFolders]);

  const add = async () => {
    if (!path.trim()) return;
    setBusy(true);
    try {
      await api.addWatchedFolder(path.trim(), true);
      setPath("");
      await loadWatchedFolders();
      useDocumentsStore.getState().startPolling();
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-ink">
        <FolderSync size={16} className="text-brand" /> Watched folders
      </div>
      <p className="mb-3 text-xs text-ink-muted">
        Any supported file added, changed, or removed in these folders is picked up automatically (checked every 30s).
      </p>
      <div className="flex gap-1.5">
        <input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="C:\Users\you\Documents\Notes"
          className="flex-1 rounded-lg border border-border bg-canvas px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand/40"
        />
        <Button size="sm" variant="primary" icon={<Plus size={14} />} onClick={add} disabled={busy}>
          Add
        </Button>
      </div>

      <div className="mt-3 space-y-1.5">
        {watchedFolders.map((f) => (
          <div key={f.id} className="flex items-center justify-between gap-2 rounded-lg bg-surface-muted px-3 py-2 text-xs">
            <span className="truncate text-ink" title={f.path}>
              {f.path}
            </span>
            <div className="flex shrink-0 items-center gap-1">
              <button
                onClick={async () => {
                  await api.scanWatchedFolder(f.id);
                  useDocumentsStore.getState().startPolling();
                }}
                title="Scan now"
                className="rounded-md p-1 text-ink-muted hover:bg-surface hover:text-ink cursor-pointer"
              >
                <RefreshCw size={13} />
              </button>
              <button
                onClick={async () => {
                  await api.removeWatchedFolder(f.id);
                  await loadWatchedFolders();
                  await useDocumentsStore.getState().load();
                }}
                title="Stop watching (removes its documents)"
                className="rounded-md p-1 text-ink-muted hover:bg-red-50 hover:text-red-600 cursor-pointer dark:hover:bg-red-900/30"
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
