import { Suspense } from "react";
import { ReviewQueue } from "@/components/review-queue";

export default function ReviewPage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Review queue</h1>
      <p className="max-w-prose text-sm text-muted">
        Every value that was withheld, flagged or not found. Open an item to read the cited page and, if
        the figure is printed there, record a correction with its page and reason.
      </p>
      <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
        <ReviewQueue />
      </Suspense>
    </section>
  );
}
