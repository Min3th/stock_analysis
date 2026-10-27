"use client";

import { useState } from "react";

/** Asks the API for a PDF of a print route and saves it; the PDF is built server-side. */
export function ExportButton({
  label,
  body,
  className = "",
}: {
  label: string;
  body: { type: "sector" | "company" | "review"; runId: string; ticker?: string };
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/exports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const detail = (await response.json().catch(() => ({}))) as { message?: string };
        throw new Error(detail.message ?? `HTTP ${response.status}`);
      }
      const name = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? "report.pdf";
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className={`inline-flex flex-col gap-1 ${className}`}>
      <button type="button" onClick={run} disabled={busy} className="rounded border border-line bg-surface px-3 py-1 text-sm hover:bg-bg disabled:opacity-60">
        {busy ? "Preparing PDF…" : label}
      </button>
      {error && (
        <span role="alert" className="max-w-xs text-xs text-red-700 dark:text-red-300">
          {error}
        </span>
      )}
    </span>
  );
}
