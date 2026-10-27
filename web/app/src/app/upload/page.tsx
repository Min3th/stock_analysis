import { UploadFlow } from "@/components/upload-flow";

export default function UploadPage() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Upload a filing</h1>
      <p className="max-w-prose text-sm text-muted">
        Use this for a report the CSE archive does not list. The file is read by the same extractor the
        pipeline uses, and you see what it found before anything is stored. An official CSE filing for
        the same period always takes priority.
      </p>
      <UploadFlow />
    </section>
  );
}
