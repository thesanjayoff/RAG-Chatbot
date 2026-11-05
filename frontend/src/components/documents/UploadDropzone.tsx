import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { useDocumentsStore } from "../../store/useDocumentsStore";

const ACCEPTED = ".pdf,.docx,.pptx,.xlsx,.csv,.md,.markdown,.txt,.html,.htm,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp";

export default function UploadDropzone() {
  const { upload } = useDocumentsStore();
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setBusy(true);
    try {
      await upload(Array.from(files), []);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        handleFiles(e.dataTransfer.files);
      }}
      onClick={() => inputRef.current?.click()}
      className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
        dragOver ? "border-brand bg-brand-soft" : "border-border bg-surface hover:bg-surface-muted"
      }`}
    >
      <UploadCloud size={28} className="text-brand" />
      <p className="text-sm font-medium text-ink">{busy ? "Uploading..." : "Drop files here or click to browse"}</p>
      <p className="text-xs text-ink-muted">PDF, Word, PowerPoint, Excel/CSV, Markdown, TXT, HTML, images</p>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
    </div>
  );
}
