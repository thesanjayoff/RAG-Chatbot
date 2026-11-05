export type DocumentStatus = "pending" | "processing" | "ready" | "error" | "skipped";

export interface DocumentRecord {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  status: DocumentStatus;
  error_message: string | null;
  progress: number;
  page_count: number;
  chunk_count: number;
  used_ocr: boolean;
  secrets_flag: boolean;
  secrets_summary: string | null;
  injection_flag: boolean;
  injection_summary: string | null;
  source_type: "upload" | "watched_folder" | "url";
  source_path: string | null;
  created_at: string;
  updated_at: string;
  tags: string[];
}

export interface ChunkRecord {
  id: string;
  chunk_index: number;
  text: string;
  section: string | null;
  page_start: number | null;
  page_end: number | null;
}

export interface Citation {
  number: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  page_start: number | null;
  page_end: number | null;
  section: string | null;
  snippet: string;
}

export interface RetrievedChunkMeta {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_start: number | null;
  page_end: number | null;
  section: string | null;
  text?: string;
  vector_score: number;
  bm25_score: number;
  fused_score: number;
  rerank_score: number | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[] | null;
  not_found?: boolean;
  used_general_knowledge?: boolean;
  created_at?: string;
  streaming?: boolean;
  retrieved?: RetrievedChunkMeta[];
  lowConfidence?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: ChatMessage[];
}

export interface FilterSpec {
  document_ids?: string[] | null;
  tag_names?: string[] | null;
  date_from?: string | null;
  date_to?: string | null;
}

export interface WatchedFolder {
  id: string;
  path: string;
  recursive: boolean;
  last_scanned_at: string | null;
}

export interface AppSettings {
  fully_local_mode: boolean;
  llm_provider: "ollama" | "anthropic";
  ollama_host: string;
  ollama_model: string;
  anthropic_model: string;
  anthropic_key_configured: boolean;
  embedding_provider: "local" | "ollama";
  local_embedding_model: string;
  use_reranker: boolean;
  refusal_score_threshold: number;
  ocr_enabled: boolean;
  max_upload_mb: number;
}
