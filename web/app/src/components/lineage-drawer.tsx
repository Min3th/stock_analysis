"use client";

import { useEffect, useRef } from "react";
import { formatExact, MISSING, toNumber, type Row } from "@/lib/format";
import type { SourceRef } from "./source-viewer";

/** Flow metrics also have a TTM lineage row named after the underlying fact. */
const FLOW_FACT: Record<string, string> = {
  Revenue: "revenue",
  "Net Profit": "net_profit",
  EPS: "eps",
  "Operating Profit": "operating_profit",
  "Operating Cash Flow": "operating_cash_flow",
};

/** `TICKER:docid:metric:page[...]`; only a 16-hex document id points at a cached PDF. */
export function parseFactId(id: string): { docId: string | null; metric: string; page: number | null } {
  const parts = id.split(":");
  const docId = /^[0-9a-f]{16}$/.test(parts[1] ?? "") ? (parts[1] as string) : null;
  const page = toNumber(parts[3] ?? null);
  return { docId, metric: parts[2] ?? "", page };
}

export function lineageRows(ratios: Row[], column: string): Row[] {
  const fact = FLOW_FACT[column];
  return ratios.filter(
    (row) => row.Metric === column || (fact !== undefined && row.Metric === `${fact} (TTM)`),
  );
}

interface Props {
  ticker: string;
  runId: string;
  column: string;
  ratios: Row[];
  facts: Row[];
  sources: Row[];
  onClose: () => void;
  onViewSource: (source: SourceRef) => void;
}

export function LineageDrawer({ ticker, runId, column, ratios, facts, sources, onClose, onViewSource }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    // No cleanup close(): it would fire the dialog's close event and dismiss it again
    // (React Strict Mode runs effects twice in development). Unmounting removes it.
    if (element && !element.open) element.showModal();
  }, [column]);

  const rows = lineageRows(ratios, column);
  const factById = new Map(facts.map((fact) => [String(fact["Fact ID"]), fact]));
  const titleByDoc = new Map(sources.map((source) => [String(source["Document ID"]), String(source.Document)]));

  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      aria-label={`How ${column} is calculated`}
      className="ml-auto mr-0 h-full max-h-none w-[min(720px,100vw)] rounded-none border-l border-line bg-surface p-0 text-ink backdrop:bg-black/40"
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-lg font-medium">
            {column} <span className="text-sm font-normal text-muted">· {ticker}</span>
          </h2>
          <button type="button" onClick={onClose} className="rounded border border-line px-2 py-1 text-sm">
            Close
          </button>
        </div>
        <div className="flex-1 space-y-6 overflow-auto p-4">
          {rows.length === 0 && (
            <p className="text-sm text-muted">The pipeline recorded no calculation for this metric.</p>
          )}
          {rows.map((row, index) => {
            const ids = String(row["Input Fact IDs"] ?? "")
              .split(";")
              .map((id) => id.trim())
              .filter(Boolean);
            return (
              <section key={index} className="space-y-2" data-testid="lineage-row">
                <h3 className="text-sm font-medium">{String(row.Metric)}</h3>
                <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-sm">
                  <dt className="text-muted">Formula</dt>
                  <dd>{String(row.Formula ?? MISSING)}</dd>
                  <dt className="text-muted">Value</dt>
                  <dd className="tabular-nums">{formatExact(row.Value)}</dd>
                  <dt className="text-muted">Numerator</dt>
                  <dd className="tabular-nums">{formatExact(row.Numerator)}</dd>
                  <dt className="text-muted">Denominator</dt>
                  <dd className="tabular-nums">{formatExact(row.Denominator)}</dd>
                  <dt className="text-muted">Period basis</dt>
                  <dd>{String(row["Period Basis"] ?? MISSING)}</dd>
                  <dt className="text-muted">Status</dt>
                  <dd>{String(row.Status ?? MISSING)}</dd>
                  {row.Notes ? (
                    <>
                      <dt className="text-muted">Notes</dt>
                      <dd>{String(row.Notes)}</dd>
                    </>
                  ) : null}
                </dl>
                <div>
                  <p className="mb-1 text-xs text-muted">Input facts</p>
                  {ids.length === 0 ? (
                    <p className="text-sm text-muted">No input fact IDs recorded.</p>
                  ) : (
                    <ul className="space-y-2">
                      {ids.map((id) => {
                        const fact = factById.get(id);
                        const parsed = parseFactId(id);
                        const title = fact ? String(fact["Source Document"]) : titleByDoc.get(parsed.docId ?? "") ?? id;
                        return (
                          <li key={id} className="rounded border border-line p-2 text-sm">
                            <p className="font-mono text-xs break-all text-muted">{id}</p>
                            {fact ? (
                              <p className="tabular-nums">
                                {String(fact.Metric)} = {formatExact(fact["Extracted Value"])} {String(fact.Unit ?? "")}
                                <span className="text-muted">
                                  {" "}
                                  · confidence {String(fact["Extraction Confidence"])} · page{" "}
                                  {String(fact["Source Page"] ?? MISSING)}
                                </span>
                              </p>
                            ) : (
                              <p className="text-muted">Derived fact (see its own lineage row).</p>
                            )}
                            {parsed.docId && (
                              <button
                                type="button"
                                className="mt-1 text-sm text-accent hover:underline"
                                onClick={() =>
                                  onViewSource({
                                    ticker,
                                    docId: parsed.docId as string,
                                    page: fact ? toNumber(fact["Source Page"]) : parsed.page,
                                    title,
                                    quote: fact ? String(fact["Source Text"] ?? "") : "",
                                    runId,
                                  })
                                }
                              >
                                View source
                              </button>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </dialog>
  );
}
