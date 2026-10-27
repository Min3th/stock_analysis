"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import Link from "next/link";
import { useMemo, useState } from "react";
import { CONFIDENCE_LABEL, COLUMN_KIND, formatValue, toNumber, type Row } from "@/lib/format";

const helper = createColumnHelper<Row>();

const DEFAULT_COLUMNS = [
  "Current Price",
  "Market Cap",
  "Revenue",
  "Net Profit",
  "EPS",
  "ROE",
  "ROA",
  "P/E",
  "P/B",
  "DPS",
  "Dividend Yield",
  "Debt-to-Equity",
];

/** Columns that are not metrics (shown separately or not as numbers). */
const SKIP = new Set(["Ticker", "Company", "Flags", "Data Confidence", "Not Applicable Metrics", "DPS Basis"]);

export function ScreeningTable({ rows, runId }: { rows: Row[]; runId: string }) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "Ticker", desc: false }]);
  const [query, setQuery] = useState("");
  const [confidence, setConfidence] = useState("all");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [allColumns, setAllColumns] = useState(false);

  const metricColumns = useMemo(() => {
    const present = new Set(rows.flatMap((row) => Object.keys(row)));
    const all = [...present].filter((name) => !SKIP.has(name) && name in COLUMN_KIND);
    return allColumns ? all : DEFAULT_COLUMNS.filter((name) => present.has(name));
  }, [rows, allColumns]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (needle && !`${row.Ticker} ${row.Company}`.toLowerCase().includes(needle)) return false;
      if (confidence !== "all" && row["Data Confidence"] !== confidence) return false;
      if (flaggedOnly && !String(row.Flags ?? "").trim()) return false;
      return true;
    });
  }, [rows, query, confidence, flaggedOnly]);

  const columns = useMemo(
    () => [
      helper.accessor((row) => String(row.Ticker ?? ""), {
        id: "Ticker",
        header: "Ticker",
        cell: (info) => (
          <Link className="text-accent hover:underline" href={`/runs/${runId}/${info.getValue()}`}>
            {info.getValue()}
          </Link>
        ),
      }),
      helper.accessor((row) => String(row.Company ?? ""), { id: "Company", header: "Company" }),
      ...metricColumns.map((name) =>
        helper.accessor((row) => toNumber(row[name]), {
          id: name,
          header: name,
          sortUndefined: "last",
          cell: (info) => (
            <span className="tabular-nums" title={String(info.row.original[name] ?? "")}>
              {formatValue(name, info.row.original[name])}
            </span>
          ),
          meta: { numeric: true },
        }),
      ),
      helper.accessor((row) => String(row["Data Confidence"] ?? ""), {
        id: "Data Confidence",
        header: "Confidence",
        cell: (info) => (
          <span className="rounded border border-line px-1.5 py-0.5 text-xs">
            {CONFIDENCE_LABEL[info.getValue()] ?? info.getValue()}
          </span>
        ),
      }),
      helper.accessor((row) => String(row["Income Period Basis"] ?? ""), {
        id: "Income Period Basis",
        header: "Income basis",
        cell: (info) => <span className="text-xs">{info.getValue() || "—"}</span>,
      }),
      helper.accessor((row) => String(row.Flags ?? "").split("; ").filter(Boolean).length, {
        id: "Flags",
        header: "Flags",
        cell: (info) => <span className="tabular-nums">{info.getValue()}</span>,
        meta: { numeric: true },
      }),
    ],
    [metricColumns, runId],
  );

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    sortDescFirst: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const control = "rounded border border-line bg-surface px-2 py-1 text-sm";
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="block text-xs text-muted">Search</span>
          <input
            className={control}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ticker or company"
          />
        </label>
        <label className="text-sm">
          <span className="block text-xs text-muted">Confidence</span>
          <select className={control} value={confidence} onChange={(e) => setConfidence(e.target.value)}>
            <option value="all">All</option>
            <option value="high">Passed checks</option>
            <option value="review">Needs review</option>
            <option value="low">Low confidence</option>
          </select>
        </label>
        <label className="flex items-center gap-2 pb-1 text-sm">
          <input type="checkbox" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} />
          Only issuers with flags
        </label>
        <label className="flex items-center gap-2 pb-1 text-sm">
          <input type="checkbox" checked={allColumns} onChange={(e) => setAllColumns(e.target.checked)} />
          All metric columns
        </label>
        <span className="pb-1 text-xs text-muted">
          {filtered.length} of {rows.length} issuers
        </span>
      </div>
      <div className="overflow-x-auto rounded border border-line bg-surface">
        <table className="w-full text-left text-sm" data-testid="screening-table">
          <thead className="border-b border-line text-xs text-muted">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const numeric = (header.column.columnDef.meta as { numeric?: boolean } | undefined)?.numeric;
                  const direction = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none"}
                      className={`px-3 py-2 font-medium ${numeric ? "text-right" : ""}`}
                    >
                      <button type="button" onClick={header.column.getToggleSortingHandler()} className="hover:underline">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {direction === "asc" ? " ▲" : direction === "desc" ? " ▼" : ""}
                      </button>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-line last:border-0">
                {row.getVisibleCells().map((cell) => {
                  const numeric = (cell.column.columnDef.meta as { numeric?: boolean } | undefined)?.numeric;
                  return (
                    <td key={cell.id} className={`px-3 py-2 ${numeric ? "text-right" : ""}`}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        Sorted by ticker unless you choose a column. “—” means no value passed the checks; the reason
        is on the issuer page and in the review queue.
      </p>
    </div>
  );
}
