"use client";

import Link from "next/link";
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { api, type Company } from "@/lib/api";
import { formatExact, MISSING } from "@/lib/format";
import { useApi } from "@/lib/use-api";

interface PreviewFact {
  metric: string;
  value: string | number;
  unit: string;
  original_value: string | number;
  original_unit: string;
  page: number;
  source_text: string;
  statement_scope: string;
  confidence: string | number;
  below_threshold: boolean;
  extraction_method: string;
  validation_status: string;
  validation_notes: string;
}

interface Preview {
  pages: number;
  parsing_methods: string[];
  parser_warnings: { page: number; strategy: string; reason: string }[];
  located_statements: Record<string, number[]>;
  facts: PreviewFact[];
  validation_issues: { metric: string; rule: string; reason: string; source_page?: number }[];
}

interface UploadRecord {
  id: string;
  ticker: string;
  kind: string;
  periodEnd: string;
  originalFilename: string;
  sha256: string;
  status: "pending" | "accepted" | "rejected";
  preview: Preview | null;
}

async function send(form: FormData): Promise<UploadRecord> {
  const response = await fetch("/api/uploads", { method: "POST", body: form });
  const body = (await response.json()) as UploadRecord & { message?: string };
  if (!response.ok) throw new Error(body.message ?? `HTTP ${response.status}`);
  return body;
}

export function UploadFlow() {
  const tickers = useApi<Company[]>("/universe-tickers");
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [ticker, setTicker] = useState("");
  const [kind, setKind] = useState("annual_report");
  const [periodEnd, setPeriodEnd] = useState("");
  const [months, setMonths] = useState("3");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [record, setRecord] = useState<UploadRecord | null>(null);
  const [done, setDone] = useState<string | null>(null);

  function pick(files: FileList | null) {
    const chosen = files?.[0] ?? null;
    setFile(chosen);
    setError(chosen && !chosen.name.toLowerCase().endsWith(".pdf") ? "Only PDF files are accepted." : null);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    pick(event.dataTransfer.files);
  }

  async function preview(event: FormEvent) {
    event.preventDefault();
    if (!file) return setError("Choose a PDF file first.");
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const form = new FormData();
      form.set("file", file);
      form.set("ticker", ticker);
      form.set("kind", kind);
      form.set("periodEnd", periodEnd);
      if (kind === "interim_statement") form.set("periodMonths", months);
      setRecord(await send(form));
    } catch (err) {
      setRecord(null);
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function decide(action: "accept" | "discard") {
    if (!record) return;
    setBusy(true);
    setError(null);
    try {
      if (action === "accept") {
        await api(`/uploads/${record.id}/accept`, { method: "POST", body: JSON.stringify({}) });
        setDone("Accepted. The next run for this company uses it as a fallback source; an official CSE filing for the same period still takes priority.");
      } else {
        await api(`/uploads/${record.id}`, { method: "DELETE" });
        setDone("Discarded. Nothing was stored.");
      }
      setRecord(null);
      setFile(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const field = "w-full rounded border border-line bg-surface px-2 py-1.5 text-sm";
  const p = record?.preview;
  return (
    <div className="space-y-6">
      <form onSubmit={preview} className="space-y-4 rounded border border-line bg-surface p-4">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`rounded border-2 border-dashed p-6 text-center text-sm ${dragging ? "border-accent bg-bg" : "border-line"}`}
        >
          <p>{file ? file.name : "Drop a PDF here, or"}</p>
          <button type="button" onClick={() => input.current?.click()} className="mt-1 text-accent hover:underline">
            choose a file
          </button>
          <input
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            aria-label="PDF file"
            data-testid="upload-input"
            onChange={(e) => pick(e.target.files)}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="space-y-1 text-sm">
            <span className="block text-muted">Company</span>
            <input
              className={field}
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              list="upload-companies"
              placeholder="ACL.N0000"
              required
            />
            <datalist id="upload-companies">
              {(tickers.data ?? []).map((company) => (
                <option key={company.ticker} value={company.ticker}>
                  {company.name}
                </option>
              ))}
            </datalist>
          </label>
          <label className="space-y-1 text-sm">
            <span className="block text-muted">Document type</span>
            <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="annual_report">Annual report</option>
              <option value="interim_statement">Interim statement</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="block text-muted">Period end</span>
            <input className={field} type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} required />
          </label>
          {kind === "interim_statement" && (
            <label className="space-y-1 text-sm">
              <span className="block text-muted">Months in the year to date</span>
              <input className={field} type="number" min={1} max={11} value={months} onChange={(e) => setMonths(e.target.value)} required />
            </label>
          )}
        </div>
        <button type="submit" disabled={busy} className="rounded bg-accent px-4 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:text-black">
          {busy && !record ? "Reading the PDF…" : "Preview extraction"}
        </button>
      </form>

      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
      {done && (
        <p role="status" className="rounded border border-line bg-surface px-3 py-2 text-sm">
          {done} <Link href="/" className="text-accent hover:underline">Back to runs</Link>
        </p>
      )}

      {record && p && (
        <section className="space-y-4" data-testid="upload-preview">
          <div>
            <h2 className="text-lg font-medium">Preview: {record.originalFilename}</h2>
            <p className="text-sm text-muted">
              {record.ticker} · {record.kind.replace("_", " ")} · period end {record.periodEnd} · {p.pages} pages · checksum{" "}
              <code>{record.sha256.slice(0, 16)}</code>
            </p>
            <p className="text-sm text-muted">
              Statements located on pages:{" "}
              {Object.entries(p.located_statements).map(([name, pages]) => `${name} ${pages.join(", ")}`).join(" · ") || "none found"}
            </p>
          </div>
          {p.parser_warnings.length > 0 && (
            <ul className="text-sm text-amber-800 dark:text-amber-300">
              {p.parser_warnings.map((w, i) => (
                <li key={i}>Page {w.page} ({w.strategy}): {w.reason}</li>
              ))}
            </ul>
          )}
          <div className="overflow-x-auto rounded border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line text-xs text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Metric</th>
                  <th className="px-3 py-2 text-right font-medium">Value</th>
                  <th className="px-3 py-2 font-medium">Scope</th>
                  <th className="px-3 py-2 text-right font-medium">Page</th>
                  <th className="px-3 py-2 text-right font-medium">Confidence</th>
                  <th className="px-3 py-2 font-medium">Source text</th>
                </tr>
              </thead>
              <tbody>
                {p.facts.map((fact) => (
                  <tr
                    key={fact.metric}
                    data-testid="preview-fact"
                    data-below={fact.below_threshold}
                    className={`border-b border-line last:border-0 ${fact.below_threshold ? "bg-warn-bg text-warn-ink" : ""}`}
                  >
                    <td className="px-3 py-2">{fact.metric}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatExact(fact.value)} <span className="text-xs">{fact.unit}</span></td>
                    <td className="px-3 py-2">{fact.statement_scope}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fact.page}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {String(fact.confidence)}
                      {fact.below_threshold && <span className="ml-1 text-xs">below threshold: would not reach screening</span>}
                    </td>
                    <td className="max-w-md px-3 py-2 font-mono text-xs break-words">{fact.source_text || MISSING}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {p.validation_issues.length > 0 && (
            <div>
              <h3 className="text-sm font-medium">Checks that did not pass</h3>
              <ul className="list-disc pl-5 text-sm">
                {p.validation_issues.map((issue, i) => (
                  <li key={i}>{issue.metric}: {issue.reason}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex gap-3">
            <button type="button" disabled={busy} onClick={() => decide("accept")} className="rounded bg-accent px-4 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:text-black">
              Accept as a source
            </button>
            <button type="button" disabled={busy} onClick={() => decide("discard")} className="rounded border border-line px-4 py-1.5 text-sm">
              Discard
            </button>
          </div>
          <p className="text-xs text-muted">
            Accepting stores the file by checksum and lists it in config/uploads.yml. Facts are extracted again
            by the normal pipeline on the next run; this preview does not change any figure.
          </p>
        </section>
      )}
    </div>
  );
}
