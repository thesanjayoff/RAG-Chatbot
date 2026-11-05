import type { ReactNode } from "react";
import type { Citation } from "./types";

const CITE_RE = /\[(\d+)\]/g;
const BOLD_RE = /(\*\*[^*]+\*\*)/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(BOLD_RE);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={`${keyPrefix}-b-${i}`}>{part.slice(2, -2)}</strong>
    ) : (
      <span key={`${keyPrefix}-t-${i}`}>{part}</span>
    ),
  );
}

/** Renders assistant/summary/comparison text: paragraphs, soft line
 * breaks, light bold support, and {citeNumber} markers turned into
 * clickable badges that jump to the source document/page. */
export function renderMessageContent(content: string, citations: Citation[] | undefined, onCiteClick: (c: Citation) => void): ReactNode {
  const citeMap = new Map((citations ?? []).map((c) => [c.number, c]));
  const paragraphs = content.split(/\n\n+/).filter((p) => p.length > 0);

  return paragraphs.map((para, pi) => {
    const lines = para.split("\n");
    return (
      <p key={pi} className={pi > 0 ? "mt-3" : ""}>
        {lines.map((line, li) => {
          const segments = line.split(CITE_RE);
          return (
            <span key={li}>
              {li > 0 && <br />}
              {segments.map((seg, si) => {
                if (si % 2 === 1) {
                  const num = Number(seg);
                  const citation = citeMap.get(num);
                  return (
                    <button
                      key={si}
                      type="button"
                      onClick={() => citation && onCiteClick(citation)}
                      disabled={!citation}
                      title={citation ? `${citation.filename}${citation.page_start ? ` — p.${citation.page_start}` : ""}` : "unknown source"}
                      className="mx-0.5 inline-flex h-5 min-w-5 translate-y-[-1px] items-center justify-center rounded-full bg-brand-soft px-1 text-[11px] font-semibold text-brand hover:bg-brand hover:text-white disabled:opacity-40 cursor-pointer"
                    >
                      {num}
                    </button>
                  );
                }
                return <span key={si}>{renderInline(seg, `${pi}-${li}-${si}`)}</span>;
              })}
            </span>
          );
        })}
      </p>
    );
  });
}
