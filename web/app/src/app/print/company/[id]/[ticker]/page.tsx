import { CompanyPrint } from "@/components/print-views";

export default async function Page({ params }: { params: Promise<{ id: string; ticker: string }> }) {
  const { id, ticker } = await params;
  return <CompanyPrint runId={id} ticker={decodeURIComponent(ticker)} />;
}
