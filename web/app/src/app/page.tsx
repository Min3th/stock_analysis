import { RunsDashboard } from "@/components/runs-dashboard";

export default function HomePage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Runs</h1>
      <p className="max-w-prose text-sm text-muted">
        Each run is the Python pipeline for one industry group and period. This page starts runs
        and shows their output; it never calculates a ratio itself.
      </p>
      <RunsDashboard />
    </section>
  );
}
