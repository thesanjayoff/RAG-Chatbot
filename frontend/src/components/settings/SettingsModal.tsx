import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import * as api from "../../lib/api";
import type { AppSettings } from "../../lib/types";
import Modal from "../common/Modal";
import Toggle from "../common/Toggle";
import Spinner from "../common/Spinner";
import Badge from "../common/Badge";

export default function SettingsModal({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [ollamaOk, setOllamaOk] = useState<boolean | null>(null);
  const [chunkCount, setChunkCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    api.getHealth().then((h) => {
      setSettings(h.settings);
      setOllamaOk(h.ollama_reachable);
      setChunkCount(h.vector_chunk_count);
      setLoading(false);
    });
  };

  useEffect(() => {
    refresh();
  }, []);

  const patch = async (p: Partial<AppSettings>) => {
    const updated = await api.updateSettings(p);
    setSettings(updated as AppSettings);
  };

  if (loading || !settings) {
    return (
      <Modal title="Settings" onClose={onClose}>
        <div className="flex items-center gap-2 py-6 text-sm text-ink-muted">
          <Spinner /> Loading...
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="Settings" onClose={onClose}>
      <div className="space-y-5">
        <section>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">Privacy</p>
          <Toggle
            checked={settings.fully_local_mode}
            onChange={(v) => patch({ fully_local_mode: v })}
            label="Fully local mode"
            description="Blocks the Anthropic provider and web-page fetching -- nothing leaves this machine"
          />
        </section>

        <section>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">Language model</p>
          <div className="flex gap-2">
            {(["ollama", "anthropic"] as const).map((p) => (
              <button
                key={p}
                disabled={p === "anthropic" && settings.fully_local_mode}
                onClick={() => patch({ llm_provider: p })}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium disabled:opacity-40 cursor-pointer ${
                  settings.llm_provider === p ? "border-brand bg-brand-soft text-brand" : "border-border text-ink-muted hover:text-ink"
                }`}
              >
                {p === "ollama" ? "Ollama (local)" : "Anthropic (hosted)"}
              </button>
            ))}
          </div>
          <div className="mt-2 flex items-center gap-2 text-xs text-ink-muted">
            {settings.llm_provider === "ollama" ? (
              <>
                Model: <code className="rounded bg-surface-muted px-1.5 py-0.5">{settings.ollama_model}</code>
                {ollamaOk === null ? null : ollamaOk ? (
                  <Badge tone="success">
                    <CheckCircle2 size={11} /> reachable
                  </Badge>
                ) : (
                  <Badge tone="danger">
                    <XCircle size={11} /> not reachable at {settings.ollama_host}
                  </Badge>
                )}
              </>
            ) : (
              <>
                Model: <code className="rounded bg-surface-muted px-1.5 py-0.5">{settings.anthropic_model}</code>
                {settings.anthropic_key_configured ? (
                  <Badge tone="success">key configured</Badge>
                ) : (
                  <Badge tone="danger">ANTHROPIC_API_KEY not set</Badge>
                )}
              </>
            )}
          </div>
        </section>

        <section>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">Retrieval</p>
          <Toggle
            checked={settings.use_reranker}
            onChange={(v) => patch({ use_reranker: v })}
            label="Cross-encoder reranking"
            description="Reranks hybrid search results for precision (always runs locally)"
          />
          <p className="mt-2 text-xs text-ink-muted">
            Embeddings: <code className="rounded bg-surface-muted px-1.5 py-0.5">{settings.embedding_provider}</code> ·{" "}
            {settings.local_embedding_model}
          </p>
          <p className="mt-1 text-xs text-ink-muted">Refusal threshold: {settings.refusal_score_threshold}</p>
        </section>

        <section>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">Index status</p>
          <p className="text-xs text-ink-muted">{chunkCount ?? "?"} chunks currently indexed.</p>
        </section>

        <p className="text-xs text-ink-muted">
          These settings apply for the current server session. For changes that persist across restarts, edit your{" "}
          <code className="rounded bg-surface-muted px-1 py-0.5">.env</code> file.
        </p>
      </div>
    </Modal>
  );
}
