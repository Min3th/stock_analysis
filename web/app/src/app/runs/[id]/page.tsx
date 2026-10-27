import { SectorView } from "@/components/sector-view";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SectorView runId={id} />;
}
