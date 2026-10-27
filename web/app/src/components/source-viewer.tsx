"use client";

import { useEffect, useRef } from "react";

export interface SourceRef {
  ticker: string;
  docId: string;
  page: number | null;
  title: string;
  quote: string;
  runId: string;
}

/**
 * The cited PDF at the cited page, beside the exact text the figure was read from.
 * The browser's own PDF viewer honours the `#page=` fragment.
 */
export function SourceViewer({ source, onClose }: { source: SourceRef; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
    return () => element?.close();
  }, [source]);

  const fragment = source.page ? `#page=${source.page}` : "";
  const url = `/api/documents/${encodeURIComponent(source.ticker)}/${source.docId}/file?run=${encodeURIComponent(source.runId)}${fragment}`;
  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      aria-label={`Source: ${source.title}`}
      className="m-auto h-[85vh] w-[min(1100px,95vw)] rounded border border-line bg-surface p-0 text-ink backdrop:bg-black/50"
    >
      <div className="flex h-full flex-col">
        <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-2">
          <div>
            <p className="text-sm font-medium">{source.title}</p>
            <p className="text-xs text-muted">
              {source.ticker} · {source.page ? `page ${source.page}` : "page not recorded"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <a href={url} target="_blank" rel="noreferrer" className="text-sm text-accent hover:underline">
              Open in a tab
            </a>
            <button type="button" onClick={onClose} className="rounded border border-line px-2 py-1 text-sm">
              Close
            </button>
          </div>
        </div>
        <div className="grid min-h-0 flex-1 gap-0 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <div className="overflow-auto border-b border-line p-4 md:border-b-0 md:border-r">
            <p className="mb-1 text-xs text-muted">Text the figure was read from</p>
            <p className="whitespace-pre-wrap break-words rounded border border-line bg-bg p-2 font-mono text-xs" data-testid="source-quote">
              {source.quote || "No source text was recorded for this value."}
            </p>
          </div>
          <iframe title={`${source.title}, page ${source.page ?? "?"}`} src={url} className="h-full w-full" />
        </div>
      </div>
    </dialog>
  );
}
