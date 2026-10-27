import { CompanyView } from "@/components/company-view";

export default async function CompanyPage({ params }: { params: Promise<{ id: string; ticker: string }> }) {
  const { id, ticker } = await params;
  return <CompanyView runId={id} ticker={decodeURIComponent(ticker)} />;
}
