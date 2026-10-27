"use client";

import { useEffect, useRef, useState } from "react";
import type { RunStatus } from "@/lib/api";

const MAX_LINES = 500;

/** Streams a run's output over server-sent events: the stored log first, then live lines. */
export function LiveLog({
  runId,
  onStatus,
}: {
  runId: string;
  onStatus?: (status: RunStatus) => void;
}) {
  const [lines, setLines] = useState<string[]>([]);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [lost, setLost] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const notify = useRef(onStatus);
  notify.current = onStatus;

  useEffect(() => {
    setLines([]);
    setStatus(null);
    setLost(false);
    const source = new EventSource(`/api/runs/${runId}/events`);
    source.addEventListener("log", (event) => {
      const line = JSON.parse((event as MessageEvent<string>).data) as string;
      setLines((previous) => [...previous, line].slice(-MAX_LINES));
    });
    source.addEventListener("status", (event) => {
      const next = JSON.parse((event as MessageEvent<string>).data) as RunStatus;
      setStatus(next);
      notify.current?.(next);
    });
    source.addEventListener("end", () => source.close());
    source.onerror = () => {
      // EventSource retries by itself; only report when it has given up.
      if (source.readyState === EventSource.CLOSED) {
        setLost(true);
      }
    };
    return () => source.close();
  }, [runId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [lines]);

  return (
    <div className="space-y-1">
      <p className="text-xs text-muted">
        Output of <code>{runId}</code>
        {status ? ` — ${status}` : ""}
        {lost ? " — connection lost" : ""}
      </p>
      <div
        role="log"
        aria-live="polite"
        aria-label="Pipeline output"
        className="max-h-72 overflow-auto rounded border border-line bg-surface p-3 font-mono text-xs leading-relaxed"
      >
        {lines.length === 0 ? (
          <span className="text-muted">Waiting for output…</span>
        ) : (
          lines.map((line, index) => (
            <div key={index} className="whitespace-pre-wrap break-all">
              {line}
            </div>
          ))
        )}
        <div ref={bottom} />
      </div>
    </div>
  );
}
