import { Suspense } from "react";
import { EquipmentView } from "./view";
import { AuthGuard } from "@/components/AuthGuard";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <AuthGuard>
      <Suspense fallback={<div className="p-5 text-sm text-[#8B98A5]">Loading…</div>}>
        <EquipmentView id={id} />
      </Suspense>
    </AuthGuard>
  );
}
