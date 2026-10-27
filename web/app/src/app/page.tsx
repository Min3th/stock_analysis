import { ApiStatus } from "@/components/api-status";

export default function HomePage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Runs</h1>
      <p className="max-w-prose text-sm text-muted">
        This app displays the output of the Python pipeline and starts its runs. It never
        calculates a ratio itself. Past runs and the run form arrive in the next step.
      </p>
      <ApiStatus />
    </section>
  );
}
