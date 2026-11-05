import type {
  AppSettings,
  ChunkRecord,
  Citation,
  Conversation,
  DocumentRecord,
  FilterSpec,
  RetrievedChunkMeta,
  WatchedFolder,
} from "./types";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail ?? body.error ?? JSON.stringify(body);
    } catch {
      /* ignore parse errors */
    }
    throw new ApiError(detail, resp.status);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

// ---------- Documents ----------

export function listDocuments() {
  return request<DocumentRecord[]>("/api/documents");
}

export function getDocument(id: string) {
  return request<DocumentRecord>(`/api/documents/${id}`);
}

export function getDocumentChunks(id: string) {
  return request<ChunkRecord[]>(`/api/documents/${id}/chunks`);
}

export function deleteDocument(id: string) {
  return request<{ status: string }>(`/api/documents/${id}`, { method: "DELETE" });
}

export function reindexDocument(id: string) {
  return request<{ status: string }>(`/api/documents/${id}/reindex`, { method: "POST" });
}

export function setDocumentTags(id: string, tags: string[]) {
  return request<DocumentRecord>(`/api/documents/${id}/tags`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tags),
  });
}

export function listAllTags() {
  return request<string[]>("/api/documents/tags/all");
}

export function documentFileUrl(id: string) {
  return `/api/documents/${id}/file`;
}

export async function uploadDocument(file: File, tags: string[] = []): Promise<{ status: string; document_id?: string; filename?: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("tags", tags.join(","));
  return request(`/api/documents/upload`, { method: "POST", body: form });
}

export function ingestUrl(url: string, tags: string[] = []) {
  return request<{ status: string; document_id?: string; filename?: string }>("/api/documents/url", {
    method: "POST",
    body: JSON.stringify({ url, tags }),
  });
}

// ---------- Watched folders ----------

export function listWatchedFolders() {
  return request<WatchedFolder[]>("/api/watched-folders");
}

export function addWatchedFolder(path: string, recursive = true) {
  return request<WatchedFolder>("/api/watched-folders", {
    method: "POST",
    body: JSON.stringify({ path, recursive }),
  });
}

export function scanWatchedFolder(id: string) {
  return request<{ status: string }>(`/api/watched-folders/${id}/scan`, { method: "POST" });
}

export function removeWatchedFolder(id: string) {
  return request<{ status: string }>(`/api/watched-folders/${id}`, { method: "DELETE" });
}

// ---------- Conversations ----------

export function listConversations() {
  return request<Conversation[]>("/api/conversations");
}

export function searchConversations(q: string) {
  return request<Conversation[]>(`/api/conversations/search?q=${encodeURIComponent(q)}`);
}

export function getConversation(id: string) {
  return request<Conversation>(`/api/conversations/${id}`);
}

export function createConversation(title = "New conversation") {
  return request<Conversation>("/api/conversations", { method: "POST", body: JSON.stringify({ title }) });
}

export function renameConversation(id: string, title: string) {
  return request<Conversation>(`/api/conversations/${id}`, { method: "PATCH", body: JSON.stringify({ title }) });
}

export function deleteConversation(id: string) {
  return request<{ status: string }>(`/api/conversations/${id}`, { method: "DELETE" });
}

export function exportConversationUrl(id: string, format: "markdown" | "pdf") {
  return `/api/export/conversation/${id}?format=${format}`;
}

// ---------- Analysis ----------

export function summarizeDocuments(documentIds: string[]) {
  return request<{ summary: string; citations: Citation[] }>("/api/summarize", {
    method: "POST",
    body: JSON.stringify({ document_ids: documentIds }),
  });
}

export function compareDocuments(idsA: string[], idsB: string[], aspect?: string) {
  return request<{ comparison: string; citations: Citation[] }>("/api/compare", {
    method: "POST",
    body: JSON.stringify({ document_ids_a: idsA, document_ids_b: idsB, aspect }),
  });
}

// ---------- Settings ----------

export function getSettings() {
  return request<AppSettings>("/api/settings");
}

export function updateSettings(patch: Partial<AppSettings>) {
  return request<AppSettings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) });
}

export function getHealth() {
  return request<{ status: string; ollama_reachable: boolean; vector_chunk_count: number | null; settings: AppSettings }>(
    "/api/settings/health",
  );
}

// ---------- Chat streaming (SSE over POST) ----------

export interface ChatRequestPayload {
  conversation_id?: string | null;
  message: string;
  filters?: FilterSpec | null;
  show_chunks: boolean;
  allow_general_knowledge: boolean;
  use_subquestions: boolean;
}

export interface ChatDonePayload {
  citations: Citation[];
  not_found: boolean;
  used_general_knowledge: boolean;
}

export interface ChatMetaPayload {
  rewritten_query: string;
  sub_questions: string[] | null;
  retrieved: RetrievedChunkMeta[];
  low_confidence: boolean;
}

export interface ChatStreamHandlers {
  onStart?: (conversationId: string) => void;
  onMeta?: (meta: ChatMetaPayload) => void;
  onDelta?: (text: string) => void;
  onDone?: (payload: ChatDonePayload) => void;
  onError?: (message: string) => void;
}

function parseSseEvent(raw: string): { event: string; data: string } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

export function streamChat(payload: ChatRequestPayload, handlers: ChatStreamHandlers): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        handlers.onError?.(`Request failed (${resp.status})`);
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx: number;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const rawEvent = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const parsed = parseSseEvent(rawEvent);
          if (!parsed) continue;
          dispatchEvent(parsed, handlers);
        }
      }
    } catch (err) {
      if ((err as DOMException)?.name !== "AbortError") {
        handlers.onError?.(err instanceof Error ? err.message : String(err));
      }
    }
  })();

  return () => controller.abort();
}

function dispatchEvent(parsed: { event: string; data: string }, handlers: ChatStreamHandlers) {
  let data: any;
  try {
    data = JSON.parse(parsed.data);
  } catch {
    return;
  }
  switch (parsed.event) {
    case "start":
      handlers.onStart?.(data.conversation_id);
      break;
    case "meta":
      handlers.onMeta?.(data as ChatMetaPayload);
      break;
    case "delta":
      handlers.onDelta?.(data.text);
      break;
    case "done":
      handlers.onDone?.(data as ChatDonePayload);
      break;
    case "error":
      handlers.onError?.(data.message);
      break;
  }
}

export { ApiError };
