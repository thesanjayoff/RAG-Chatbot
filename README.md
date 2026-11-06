# RAG Chatbot — chat with your own documents, locally

A personal, local-first "chat with my documents" app: drop in PDFs, Word/PowerPoint/Excel
files, Markdown, HTML, images, or web pages, and ask questions that are answered **only**
from what's actually in them, with clickable citations back to the source page/passage.
No accounts, no cloud database, no multi-user anything — it's a single-user tool that
stores everything in a local SQLite database and a local vector index.

Built from scratch (not a fork of PrivateGPT/LlamaIndex/etc. — see [Inspirations](#inspirations-studied-not-copied)
below) as a FastAPI + React app.

## Features

**Ingestion**
- PDF (text and scanned/OCR), Word, PowerPoint, Excel/CSV, Markdown, TXT, HTML, and images
  with text, plus folder watching and direct URL ingestion.
- Structure-aware parsing: headings (via font-size heuristics), tables (markdown-rendered),
  page numbers, and sections are preserved, not flattened into one blob.
- Smart chunking with overlap, carrying file/page/section metadata on every chunk.
- Local embeddings (sentence-transformers) or Ollama embeddings; local LLM via Ollama, or a
  hosted model (Claude) via an API key in `.env` — your choice. A `FULLY_LOCAL_MODE` flag
  disables the hosted path entirely so nothing ever leaves the machine.
- Incremental sync: watched folders re-index changed files by content hash, skip unchanged
  ones, and remove documents that were deleted from disk.
- Per-file ingestion status and progress in the Library tab, with real error messages.

**Retrieval & answering**
- Hybrid retrieval (dense vector search + BM25) fused by normalized weighted scoring, then
  reranked with a cross-encoder.
- Query rewriting from chat history, and optional sub-question decomposition for compound
  questions.
- Answers are grounded **only** in retrieved passages; every claim carries a citation that
  opens the source document at the right page with the passage highlighted. Below a
  confidence threshold, the bot says "I couldn't find that in your documents" instead of
  guessing — deterministically, without even calling the LLM.
- Streaming responses over SSE, with a toggle to inspect the raw retrieved chunks and their
  scores.
- Filter retrieval by document, tag, or date range.

**App**
- Multi-conversation chat with history search, a document library (preview/tag/delete/
  re-index), a built-in PDF viewer with highlight-on-open, one-click summaries, a
  document-compare mode, and Markdown/PDF export of a conversation with its citations.
- Dark/light mode, keyboard shortcuts, and explicit empty/error states throughout.

**Security** (see [Security](#security) below for the full, honest rundown)
- Every document is treated as untrusted. Instructions embedded in a document can never
  change the model's behavior — delimited data blocks, a per-request random nonce, and an
  independent heuristic flag that surfaces injection attempts to the user instead of hiding them.
- Hidden text (zero-width characters, white-on-white, sub-1.5pt fonts, HTML
  `display:none`/`visibility:hidden`, HTML comments, Word's hidden-run flag) is stripped
  before anything reaches the model.
- Content-based file-type sniffing (not extension trust), size limits, zip-bomb protection,
  and parsing in a process-isolated, network-disabled sandbox.
- Optional secrets/PII scan before indexing (AWS/GitHub/Slack/Anthropic-style keys, private
  key blocks, JWTs, SSNs, card numbers, emails), with the match flagged in the Library.
- Binds to `127.0.0.1` by default; API keys live in `.env`; logs redact detected secrets.

## Quick start

Prerequisites: Python 3.11+, Node 18+, and (for the default fully-local setup)
[Ollama](https://ollama.com) running locally.

```bash
# 1. Pull a local model (any Ollama chat model works; this is the default)
ollama pull qwen3:4b-instruct

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
python run.py                   # serves the API on http://127.0.0.1:8731

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev                     # dev server on http://localhost:5173, proxies /api to the backend

# 4. Optional: seed the demo workspace so there's something to ask about immediately
cd backend
python ../scripts/seed_demo.py --with-injection-tests
```

Open `http://localhost:5173` and try: *"What is the Falcon-3's battery life?"* or *"What
was Northwind's total revenue in Q3 2026?"*

### Running fully local (nothing ever leaves the machine)

Set `FULLY_LOCAL_MODE=true` in `.env` (copy `.env.example` first) and make sure
`EMBEDDING_PROVIDER` and `LLM_PROVIDER` are both `local`/`ollama`. In this mode the Anthropic
client refuses to construct and URL ingestion is disabled outright, not just hidden in the UI.

### Using a hosted model instead

Leave `FULLY_LOCAL_MODE=false`, set `LLM_PROVIDER=anthropic`, and put your key in
`ANTHROPIC_API_KEY`. Embeddings can stay local even when the LLM is hosted.

### Production build

```bash
cd frontend
npm run build                   # writes frontend/dist
cd ../backend
python run.py                   # now also serves the built frontend at http://127.0.0.1:8731
```

## Running tests

```bash
cd backend
pytest -q
```

49 tests cover parsing (every format, including hidden-text stripping and OCR fallback),
chunking (including oversized-table splitting), citation mapping (including the streaming
case where a `{cite:...}` tag is split across tokens), retrieval, and injection defenses.

## Evaluation

`eval/dataset.jsonl` has 57 hand-written QA pairs grounded in the seeded "Northwind Robotics"
demo workspace (`scripts/generate_demo_docs.py`), deliberately covering the tricky cases:
table lookups, facts that only make sense combined across two pages or two documents, exact
numbers, out-of-corpus "trap" questions that should be refused, and three documents carrying
real prompt-injection payloads (a hidden-tiny-font PDF instruction, an HTML comment, and a
`display:none` block).

`eval/run_eval.py` re-ingests that corpus from scratch into an isolated index for each
configuration below, runs every question through the real retrieval + answer pipeline (not a
mock), and scores:

- **Retrieval hit-rate** — did the top-k retrieved chunks include the expected source document?
- **Answer correctness** — fraction of expected facts (numbers, names) present in the answer.
- **Citation accuracy** — when the model answers, does every citation point at the correct document?
- **Refusal accuracy** — on the out-of-corpus questions, did it actually refuse instead of guessing?
- **False-refusal rate** — on answerable questions, how often did it refuse by mistake?
- **Injection-defense rate** — on the 3 injection documents, did the answer avoid the planted
  payload (leaking a fake password, recommending a fake "only legitimate supplier", claiming
  the company is bankrupt) while still answering the real question correctly?

```bash
cd backend
python ../eval/run_eval.py                                   # all 3 configs, full dataset
python ../eval/run_eval.py --configs vector_only_chunk400     # just one config
python ../eval/run_eval.py --limit 10                          # quick smoke test
```

### Results

<!-- EVAL_RESULTS_TABLE -->

Each config re-ingests the same 10 documents from scratch with the settings below, so the
comparison isolates the retrieval strategy (and chunk size) as the only variable:

| Config | What changes |
|---|---|
| Hybrid + reranker, chunk=400 tok | Default: vector + BM25 fused 50/50, cross-encoder reranked, ~400-token chunks |
| Vector-only, chunk=400 tok | Same chunking, but BM25 weight is zeroed out and the reranker is skipped — pure dense retrieval |
| Hybrid + reranker, chunk=120 tok | Same retrieval strategy as the default, with much smaller (~120-token) chunks |

Full per-question results (including every answer, citation, and verdict) are in
`eval/results/<config>.json`.

## Security

This is a personal tool handling your own files, built with the threat model of "a document
you open could be actively hostile," not just malformed:

- **Prompt injection**: retrieved text is wrapped in `<DOCUMENT_DATA_{random-nonce}>` blocks
  (a fresh nonce every request, so a document can't pre-guess and spoof the delimiter), and
  the system prompt explicitly tells the model that content inside is data, never
  instructions — even if it claims to be a system message or asks the model to ignore prior
  instructions. A second, independent heuristic scan flags injection-style phrases to the
  user regardless of what the model does with them. The model is never given tools or the
  ability to take actions from document content — it only reads and answers.
- **Hidden text**: stripped before anything reaches the model or the index — zero-width
  Unicode characters, sub-1.5pt or white-on-white PDF text, HTML `display:none`/
  `visibility:hidden` and comments, and Word's hidden-run flag.
- **Untrusted files**: type is sniffed from content (via `filetype` + custom sniffing), not
  trusted from the extension; uploads are size-capped; zip-based formats (docx/pptx/xlsx) are
  checked for decompression-bomb ratios before being opened.
- **Sandboxed parsing**: every file is parsed in a separate worker process with outbound
  sockets patched to raise on `connect()`, so a malicious file can't make the parser phone
  home even via a library bug. This is defense in depth, not a full OS sandbox — there's no
  seccomp/network-namespace isolation, so treat it as raising the bar, not a guarantee.
- **Secrets/PII**: an optional scan flags likely API keys, private key blocks, JWTs, SSNs,
  card numbers, and similar before indexing, surfaced in the Library so you can decide
  whether to mask or skip a file.
- **Network defaults**: binds to `127.0.0.1` only; `FULLY_LOCAL_MODE` disables the hosted LLM
  and URL ingestion outright; API keys are read from environment variables, never hardcoded;
  logs redact detected secrets before they're written.

What this is *not*: a hardened multi-tenant system, a replacement for OS-level sandboxing, or
proof against a sufficiently novel injection technique the heuristics don't recognize —
defense in depth reduces risk, it doesn't eliminate it.

## Architecture

```
backend/app/
  ingestion/     parsers (pdf/docx/pptx/xlsx/csv/html/md/image/web) -> chunker -> pipeline
  retrieval/     embeddings, vector store (numpy flat index), BM25, cross-encoder reranker, hybrid fusion
  llm/           Ollama / Anthropic clients behind one interface, injection-resistant prompts
  services/      answer_engine (RAG orchestration + streaming), citation mapping, summarize/compare
  security/      file validation, secrets/PII scanning, sanitization + injection-phrase detection
  api/           FastAPI routers (documents, chat, conversations, analysis, settings, export)
frontend/src/
  store/         zustand stores (chat streaming state machine, documents, viewer, theme)
  components/    chat, documents, viewer (PDF.js), analysis modals, settings
```

Why a few choices look unusual:
- **No chromadb/hnswlib** — those need a C++ build toolchain to compile on Windows, which is
  real friction for a "just `pip install` it" personal tool. `app/retrieval/vectorstore.py`
  is a small numpy flat-index (cosine similarity via normalized dot product) instead; at
  personal-document-collection scale (thousands, not millions, of chunks) a brute-force scan
  is a few milliseconds and much easier to reason about.
- **EasyOCR, not Tesseract** — pure Python + bundled models, no system binary to separately
  install. OCR models are warmed up once at server startup (in the main process, which has
  network access) specifically so the network-sandboxed parsing worker never needs the
  network, even on the very first scanned document.
- **Custom SSE, not EventSource** — the chat endpoint is a `POST` (it needs the conversation
  history and filters in the body), and the browser's native `EventSource` only supports
  `GET`. Both the server generator and the browser-side parser are hand-rolled.

## Inspirations (studied, not copied)

The design was informed by reading how these projects approach the same problem, but no code
was copied from any of them — this is an original implementation:
[PrivateGPT](https://github.com/zylon-ai/private-gpt),
[LlamaIndex](https://github.com/run-llama/llama_index),
[Haystack](https://github.com/deepset-ai/haystack),
[AnythingLLM](https://github.com/Mintplex-Labs/anything-llm),
[Open WebUI](https://github.com/open-webui/open-webui),
[RAGFlow](https://github.com/infiniflow/ragflow),
[Docling](https://github.com/DS4SD/docling),
[Unstructured](https://github.com/Unstructured-IO/unstructured),
[Ragas](https://github.com/explodinggradients/ragas) (eval methodology),
and NotebookLM/Perplexity for UX patterns (citation-first answers, source panel).

## Known limitations

- Local generation speed depends entirely on your hardware — the default `qwen3:4b-instruct`
  via Ollama on CPU answers a RAG question in roughly 5–50 seconds; a GPU or a hosted model
  will be much faster.
- The sandboxed parsing worker is defense in depth (network access disabled, process
  isolation), not a full OS-level sandbox.
- UI changes were verified via type-checking (`tsc -b`), a production build (`vite build`),
  and live backend smoke tests (curl/SSE against a running server) — not through interactive
  in-browser testing, since no browser-automation tool was available in the build environment.
