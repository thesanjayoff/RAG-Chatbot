import { useState } from "react";
import { Globe, Plus } from "lucide-react";
import { useDocumentsStore } from "../../store/useDocumentsStore";
import Button from "../common/Button";

export default function UrlIngestForm() {
  const { ingestUrl } = useDocumentsStore();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await ingestUrl(url.trim(), []);
      setUrl("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-ink">
        <Globe size={16} className="text-brand" /> Add a web page
      </div>
      <div className="flex gap-1.5">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="https://example.com/article"
          className="flex-1 rounded-lg border border-border bg-canvas px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand/40"
        />
        <Button size="sm" variant="primary" icon={<Plus size={14} />} onClick={submit} disabled={busy}>
          Fetch
        </Button>
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <p className="mt-2 text-xs text-ink-muted">Disabled in fully-local mode (it requires an outbound request).</p>
    </div>
  );
}
