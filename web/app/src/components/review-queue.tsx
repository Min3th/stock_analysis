"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, type Run } from "@/lib/api";
import { MISSING, toNumber, type Row } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const UNITS = ["LKR", "LKR '000", "LKR million", "LKR billion", "LKR/share", "shares", "ratio"];

interface Correction {
  correctionId: string;
  superseded: boolean;
  value: string;
  unit: string;
  reason: string;
}

const isMetricName = (value: string) => /^[a-z][a-z_]{1,39}$/.test(value);

function CorrectionForm({ item, sources, runId, onSaved }: { item: Row; sources: Row[]; runId: string; onSaved: (id: string) => void }) {
  const ticker = String(item.Ticker);
  const period = String(item["Financial Period"] ?? "").slice(0, 10);
  const documents = sources.filter((s) => ["annual_report", "interim_statement"].includes(String(s.Type)));
  const preferred =
    String(item["Source Document"] ?? "") ||
    String(documents.find((d) => String(d["Period End"]).slice(0, 10) === period && d.Type === "annual_report")?.Document ?? documents[0]?.Document ?? "");
  const [metric, setMetric] = useState(isMetricName(String(item.Metric)) ? String(item.Metric) : "");
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("LKR");
  const [document, setDocument] = useState(preferred);
  const [page, setPage] = useState(String(toNumber(item["Source Page"]) ?? ""));
  const [scope, setScope] = useState("group");
  const [reason, setReason] = useState("");
  const [sourceText, setSourceText] = useState(String(item["Source Text"] ?? "").slice(0, 400));
  const [supersedes, setSupersedes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const existing = useApi<Correction[]>(metric ? `/corrections?ticker=${encodeURIComponent(ticker)}&metric=${metric}` : null);
  const active = (existing.data ?? []).filter((c) => !c.superseded);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = await api<{ correctionId: string }>("/corrections", {
        method: "POST",
        body: JSON.stringify({ ticker, metric, value, unit, periodEnd: period, document, sourcePage: Number(page), scope, reason, sourceText: sourceText || undefined, supersedes: supersedes || undefined }),
      });
      onSaved(saved.correctionId);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const field = "w-full rounded border border-line bg-surface px-2 py-1.5 text-sm";
  return (
    <form onSubmit={submit} className="space-y-3 rounded border border-line bg-surface p-3" aria-label="Add a correction">
      <h3 className="text-sm font-medium">Add a correction for {ticker}</h3>
      <p className="text-xs text-muted">
        Type the figure exactly as printed on the cited page. The original extraction stays on record, and the
        correction is applied the next time this company is run (run {runId.slice(0, 14)}… is unchanged).
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-sm">
          <span className="block text-xs text-muted">Metric</span>
          <input className={field} value={metric} onChange={(e) => setMetric(e.target.value)} placeholder="net_profit" required />
        </label>
        <label className="text-sm">
          <span className="block text-xs text-muted">Period end</span>
          <input className={field} value={period} readOnly aria-readonly />
        </label>
        <label className="text-sm">
          <span className="block text-xs text-muted">Value as printed</span>
          <input className={field} value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" placeholder="-1,250.5" required />
        </label>
        <label className="text-sm">
          <span className="block text-xs text-muted">Unit</span>
          <select className={field} value={unit} onChange={(e) => setUnit(e.target.value)}>
            {UNITS.map((u) => (
              <option key={u}>{u}</option>
            ))}
          </select>
        </label>
        <label className="text-sm sm:col-span-2">
          <span className="block text-xs text-muted">Document</span>
          <select className={field} value={document} onChange={(e) => setDocument(e.target.value)} required>
            {documents.map((d) => (
              <option key={String(d["Document ID"])} value={String(d.Document)}>
                {String(d.Document)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-xs text-muted">Page</span>
          <input className={field} type="number" min={1} value={page} onChange={(e) => setPage(e.target.value)} required />
        </label>
        <label className="text-sm">
          <span className="block text-xs text-muted">Statement scope</span>
          <select className={field} value={scope} onChange={(e) => setScope(e.target.value)}>
            <option>group</option>
            <option>company</option>
            <option>primary</option>
            <option>unknown</option>
          </select>
        </label>
      </div>
      <label className="block text-sm">
        <span className="block text-xs text-muted">Reason</span>
        <input className={field} value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} required />
      </label>
      <label className="block text-sm">
        <span className="block text-xs text-muted">Text copied from the page (optional)</span>
        <textarea className={field} rows={2} value={sourceText} onChange={(e) => setSourceText(e.target.value)} />
      </label>
      {active.length > 0 && (
        <label className="block text-sm">
          <span className="block text-xs text-muted">Replaces an earlier correction (kept on record, marked superseded)</span>
          <select className={field} value={supersedes} onChange={(e) => setSupersedes(e.target.value)}>
            <option value="">None: this is a new correction</option>
            {active.map((c) => (
              <option key={c.correctionId} value={c.correctionId}>
                {c.correctionId}: {c.value} {c.unit}
              </option>
            ))}
          </select>
        </label>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
      <button type="submit" disabled={busy} className="rounded bg-accent px-4 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:text-black">
        {busy ? "Saving…" : "Save correction"}
      </button>
    </form>
  );
}

export function ReviewQueue() {
  const params = useSearchParams();
  const runs = useApi<Run[]>("/runs");
  const finished = useMemo(() => (runs.data ?? []).filter((r) => r.status === "ok"), [runs.data]);
  const [runId, setRunId] = useState<string | null>(params.get("run"));
  useEffect(() => {
    if (!runId && finished[0]) setRunId(finished[0].id);
  }, [runId, finished]);

  const review = useApi<Row[]>(runId ? `/runs/${runId}/review` : null);
  const sources = useApi<Row[]>(runId ? `/runs/${runId}/sources` : null);
  const [rule, setRule] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const items = review.data ?? [];
  const rules = useMemo(() => [...new Set(items.map((i) => String(i["Validation Rule"])))].sort(), [items]);
  const visible = items
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => rule === "all" || item["Validation Rule"] === rule)
    .filter(({ item }) => `${item.Ticker} ${item.Company} ${item.Metric} ${item["Reason for Uncertainty"]}`.toLowerCase().includes(query.toLowerCase()));
  const current = selected !== null ? items[selected] : undefined;

  const docId = current
    ? String((sources.data ?? []).find((s) => s.Ticker === current.Ticker && s.Document === current["Source Document"] && ["annual_report", "interim_statement"].includes(String(s.Type)))?.["Document ID"] ?? "")
    : "";
  const page = current ? toNumber(current["Source Page"]) : null;

  const control = "rounded border border-line bg-surface px-2 py-1 text-sm";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="block text-xs text-muted">Run</span>
          <select className={control} value={runId ?? ""} onChange={(e) => { setRunId(e.target.value); setSelected(null); }}>
            {finished.map((r) => (
              <option key={r.id} value={r.id}>
                {r.sector} · {r.period} · {r.ticker ?? "group"} · {new Date(r.createdAt).toLocaleString()}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-xs text-muted">Reason</span>
          <select className={control} value={rule} onChange={(e) => setRule(e.target.value)}>
            <option value="all">All</option>
            {rules.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-xs text-muted">Search</span>
          <input className={control} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ticker, metric or text" />
        </label>
        <span className="pb-1 text-xs text-muted">{visible.length} of {items.length} items</span>
      </div>

      {!runs.loading && finished.length === 0 && <p className="text-sm text-muted">No completed run yet. <Link className="text-accent hover:underline" href="/">Start one</Link>.</p>}
      {saved && (
        <p role="status" className="rounded border border-line bg-surface px-3 py-2 text-sm">
          Correction <code>{saved}</code> saved. It is applied on the next run of that company.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="max-h-[75vh] overflow-auto rounded border border-line bg-surface">
          <table className="w-full text-left text-sm" data-testid="review-table">
            <thead className="sticky top-0 border-b border-line bg-surface text-xs text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">Ticker</th>
                <th className="px-3 py-2 font-medium">Metric</th>
                <th className="px-3 py-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {visible.map(({ item, index }) => (
                <tr key={index} className={`border-b border-line last:border-0 ${selected === index ? "bg-bg" : ""}`}>
                  <td className="px-3 py-2">
                    <button type="button" className="text-accent hover:underline" onClick={() => { setSelected(index); setSaved(null); }}>
                      {String(item.Ticker)}
                    </button>
                  </td>
                  <td className="px-3 py-2">{String(item.Metric)}</td>
                  <td className="px-3 py-2">
                    <span className="block text-xs text-muted">{String(item["Validation Rule"])}</span>
                    <span className="line-clamp-2 text-xs">{String(item["Reason for Uncertainty"] ?? "")}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="space-y-3">
          {!current && <p className="text-sm text-muted">Select an item to see its page and add a correction.</p>}
          {current && runId && (
            <>
              <div className="rounded border border-line bg-surface p-3 text-sm" data-testid="review-detail">
                <p className="font-medium">
                  {String(current.Company)} · {String(current.Metric)} · {String(current["Financial Period"] ?? "").slice(0, 10) || MISSING}
                </p>
                <p className="text-muted">{String(current["Reason for Uncertainty"] ?? "")}</p>
                {current["Candidate Values"] ? <p className="mt-1 text-xs">Candidate values: {String(current["Candidate Values"])}</p> : null}
                {current["Source Text"] ? <p className="mt-1 rounded border border-line bg-bg p-2 font-mono text-xs break-words">{String(current["Source Text"])}</p> : null}
                <p className="mt-1 text-xs text-muted">{String(current["Source Document"] || "No source document")} · page {page ?? MISSING}</p>
              </div>
              {docId ? (
                <iframe
                  title={`${String(current["Source Document"])}, page ${page ?? 1}`}
                  src={`/api/documents/${current.Ticker}/${docId}/file?run=${runId}#page=${page ?? 1}`}
                  className="h-[420px] w-full rounded border border-line"
                />
              ) : (
                <p className="text-xs text-muted">No cited page for this item (the value was not found in the document).</p>
              )}
              <CorrectionForm key={`${runId}-${selected}`} item={current} sources={(sources.data ?? []).filter((s) => s.Ticker === current.Ticker)} runId={runId} onSaved={setSaved} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
