import { SectorPrint } from "@/components/print-views";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SectorPrint runId={id} />;
}
