"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, currentPeriodLabel, type Company, type Group } from "@/lib/api";

export function RunForm({ onStarted }: { onStarted: (runId: string) => void }) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [sector, setSector] = useState("Capital Goods");
  const [period, setPeriod] = useState(currentPeriodLabel());
  const [ticker, setTicker] = useState("");
  const [offline, setOffline] = useState(false);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Group[]>("/universe/groups")
      .then(setGroups)
      .catch((err: Error) => setError(err.message));
  }, []);

  const cached = groups.find((group) => group.name === sector)?.cached ?? false;

  useEffect(() => {
    setTicker("");
    setCompanies([]);
    if (!cached) {
      setOffline(false);
      return;
    }
    api<{ companies: Company[] }>(`/universe/${encodeURIComponent(sector)}`)
      .then((body) => setCompanies(body.companies))
      .catch(() => setCompanies([]));
  }, [sector, cached]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { runId } = await api<{ runId: string }>("/runs", {
        method: "POST",
        body: JSON.stringify({ sector, period, ticker: ticker || undefined, offline }),
      });
      onStarted(runId);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const field = "w-full rounded border border-line bg-surface px-2 py-1.5 text-sm";
  return (
    <form onSubmit={submit} className="space-y-3 rounded border border-line bg-surface p-4">
      <h2 className="text-lg font-medium">Start a run</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-1 text-sm">
          <span className="block text-muted">Industry group</span>
          <select className={field} value={sector} onChange={(e) => setSector(e.target.value)}>
            {(groups.length ? groups : [{ name: sector, slug: "", cached: false }]).map((group) => (
              <option key={group.name} value={group.name}>
                {group.name}
                {group.cached ? " (cached)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="block text-muted">Period label</span>
          <input
            className={field}
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            pattern="20\d{2}(Q[1-4]|q[1-4])?"
            title="For example 2026Q3 or 2026"
            required
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="block text-muted">Company (optional)</span>
          <input
            className={field}
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            list="run-form-companies"
            placeholder="ACL.N0000"
            pattern="[A-Z]+\.[NXRWP]\d{4}|"
            title="A CSE ticker such as ACL.N0000"
          />
          <datalist id="run-form-companies">
            {companies.map((company) => (
              <option key={company.ticker} value={company.ticker}>
                {company.name}
              </option>
            ))}
          </datalist>
        </label>
        <label className="flex items-start gap-2 pt-6 text-sm">
          <input
            type="checkbox"
            checked={offline}
            disabled={!cached}
            onChange={(e) => setOffline(e.target.checked)}
            className="mt-1"
          />
          <span>
            Offline (cache only)
            <span className="block text-xs text-muted">
              {cached
                ? "Reads only data already downloaded."
                : "Needs a cached universe: run this group once online first."}
            </span>
          </span>
        </label>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-accent px-4 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:text-black"
      >
        {busy ? "Starting…" : "Start run"}
      </button>
    </form>
  );
}
