import { useEffect, useMemo, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "pdfjs-dist/web/pdf_viewer.css";
import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";
import { useViewerStore } from "../../store/useViewerStore";
import { documentFileUrl, getDocumentChunks } from "../../lib/api";
import type { ChunkRecord } from "../../lib/types";
import Spinner from "../common/Spinner";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

function normalize(s: string): string {
  return s.toLowerCase().replace(/\s+/g, " ").trim();
}

async function highlightMatch(textLayer: pdfjsLib.TextLayer, snippet: string | null | undefined, container: HTMLDivElement) {
  if (!snippet) return;
  const itemsStr = textLayer.textContentItemsStr;
  const divs = textLayer.textDivs;
  const target = normalize(snippet).slice(0, 70);
  if (!target) return;

  let joined = "";
  const offsets: number[] = [];
  for (const s of itemsStr) {
    offsets.push(joined.length);
    joined += normalize(s) + " ";
  }
  const idx = joined.indexOf(target);
  if (idx === -1) return;

  let startItem = 0;
  while (startItem < offsets.length - 1 && offsets[startItem + 1] <= idx) startItem++;
  const endPos = idx + target.length;
  let endItem = startItem;
  while (endItem < offsets.length - 1 && offsets[endItem + 1] < endPos) endItem++;

  for (let i = startItem; i <= endItem && i < divs.length; i++) {
    divs[i].classList.add("rag-highlight");
  }
  divs[startItem]?.scrollIntoView({ block: "center", behavior: "smooth" });
  container.querySelectorAll(".rag-highlight").forEach(() => {});
}

function PdfViewer({ documentId, initialPage, highlightText }: { documentId: string; initialPage: number; highlightText?: string | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const [pdfDoc, setPdfDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(initialPage || 1);
  const [numPages, setNumPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const task = pdfjsLib.getDocument({ url: documentFileUrl(documentId) });
    task.promise
      .then((doc) => {
        if (cancelled) return;
        setPdfDoc(doc);
        setNumPages(doc.numPages);
        setPage(Math.min(Math.max(initialPage || 1, 1), doc.numPages));
      })
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : String(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
      task.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId]);

  useEffect(() => {
    if (!pdfDoc) return;
    let cancelled = false;
    (async () => {
      const pageObj = await pdfDoc.getPage(page);
      if (cancelled) return;
      const naturalViewport = pageObj.getViewport({ scale: 1 });
      const containerWidth = canvasRef.current?.parentElement?.clientWidth ?? 760;
      const scale = Math.min(containerWidth / naturalViewport.width, 1.8);
      const viewport = pageObj.getViewport({ scale });

      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      await pageObj.render({ canvas, canvasContext: ctx, viewport }).promise;
      if (cancelled) return;

      const textLayerDiv = textLayerRef.current;
      if (textLayerDiv) {
        textLayerDiv.innerHTML = "";
        textLayerDiv.style.width = `${viewport.width}px`;
        textLayerDiv.style.height = `${viewport.height}px`;
        const textLayer = new pdfjsLib.TextLayer({
          textContentSource: pageObj.streamTextContent(),
          container: textLayerDiv,
          viewport,
        });
        await textLayer.render();
        if (cancelled) return;
        if (page === initialPage) {
          highlightMatch(textLayer, highlightText, textLayerDiv);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pdfDoc, page, highlightText, initialPage]);

  if (error) return <p className="p-6 text-sm text-red-600">Could not load PDF: {error}</p>;

  return (
    <div className="flex flex-1 flex-col items-center overflow-y-auto bg-canvas">
      <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-surface px-3 py-2">
        <button
          disabled={page <= 1}
          onClick={() => setPage((p) => p - 1)}
          className="rounded-lg p-1 text-ink-muted hover:bg-surface-muted disabled:opacity-30 cursor-pointer"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="text-xs text-ink-muted">
          Page {page} of {numPages || "?"}
        </span>
        <button
          disabled={page >= numPages}
          onClick={() => setPage((p) => p + 1)}
          className="rounded-lg p-1 text-ink-muted hover:bg-surface-muted disabled:opacity-30 cursor-pointer"
        >
          <ChevronRight size={16} />
        </button>
      </div>
      <div className="relative my-4 shadow-sm">
        {loading && (
          <div className="flex h-64 w-64 items-center justify-center">
            <Spinner />
          </div>
        )}
        <canvas ref={canvasRef} className="block" />
        <div ref={textLayerRef} className="textLayer absolute left-0 top-0" />
      </div>
      <style>{`.rag-highlight { background: color-mix(in srgb, #facc15 55%, transparent); border-radius: 2px; }`}</style>
    </div>
  );
}

function ChunkViewer({ documentId, highlightText }: { documentId: string; highlightText?: string | null }) {
  const [chunks, setChunks] = useState<ChunkRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const activeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getDocumentChunks(documentId)
      .then(setChunks)
      .finally(() => setLoading(false));
  }, [documentId]);

  const activeIndex = useMemo(() => {
    if (!highlightText) return -1;
    const target = normalize(highlightText).slice(0, 60);
    return chunks.findIndex((c) => normalize(c.text).includes(target));
  }, [chunks, highlightText]);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeIndex]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5">
      <div className="mx-auto max-w-2xl space-y-3">
        {chunks.map((c, i) => (
          <div
            key={c.id}
            ref={i === activeIndex ? activeRef : undefined}
            className={`rounded-xl border px-4 py-3 text-sm whitespace-pre-wrap ${
              i === activeIndex ? "border-brand bg-brand-soft" : "border-border bg-surface"
            }`}
          >
            {(c.section || c.page_start) && (
              <p className="mb-1 text-xs font-medium text-ink-muted">
                {c.section}
                {c.page_start ? ` ${c.section ? "· " : ""}p.${c.page_start}` : ""}
              </p>
            )}
            <p className="text-ink">{c.text}</p>
          </div>
        ))}
        {chunks.length === 0 && <p className="text-sm text-ink-muted">No extracted text to show for this file.</p>}
      </div>
    </div>
  );
}

export default function DocumentViewerModal() {
  const { target, close } = useViewerStore();
  if (!target) return null;

  const isPdf = target.fileType === "pdf";
  const isImage = target.fileType === "image";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 animate-fade-in" onMouseDown={close}>
      <div
        className="flex h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-surface shadow-xl border border-border"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <p className="truncate text-sm font-medium text-ink">{target.filename}</p>
          <div className="flex items-center gap-1">
            <a
              href={documentFileUrl(target.documentId)}
              download={target.filename}
              className="rounded-lg p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink cursor-pointer"
              title="Download original file"
            >
              <Download size={16} />
            </a>
            <button onClick={close} className="rounded-lg p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink cursor-pointer">
              <X size={18} />
            </button>
          </div>
        </div>

        {isPdf ? (
          <PdfViewer documentId={target.documentId} initialPage={target.page || 1} highlightText={target.highlightText} />
        ) : isImage ? (
          <div className="flex flex-1 flex-col overflow-y-auto">
            <div className="flex justify-center bg-canvas p-4">
              <img src={documentFileUrl(target.documentId)} alt={target.filename} className="max-h-[50vh] rounded-lg border border-border" />
            </div>
            <ChunkViewer documentId={target.documentId} highlightText={target.highlightText} />
          </div>
        ) : (
          <ChunkViewer documentId={target.documentId} highlightText={target.highlightText} />
        )}
      </div>
    </div>
  );
}
