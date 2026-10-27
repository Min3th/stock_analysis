"use client";

import { useEffect, useState } from "react";

interface Health {
  status: string;
  pipelineFound: boolean;
  pythonBin: string;
}

export function ApiStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then(setHealth)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) {
    return (
      <p role="alert" className="text-sm text-red-700">
        The local API is not reachable ({error}). Start it with <code>npm run dev:api</code>.
      </p>
    );
  }
  if (!health) {
    return <p className="text-sm text-muted">Checking the local API…</p>;
  }
  return (
    <p className="text-sm" data-testid="api-status">
      API {health.status}. Pipeline {health.pipelineFound ? "found" : "not found"} (
      <code>{health.pythonBin}</code>).
    </p>
  );
}
