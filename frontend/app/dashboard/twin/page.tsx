"use client";
import dynamic from "next/dynamic";
import { AuthGuard } from "@/components/AuthGuard";

const PlantTwin3D = dynamic(() => import("@/components/PlantTwin3D"), {
  ssr: false,
  loading: () => (
    <div className="h-[calc(100vh-12rem)] grid place-items-center text-sm text-[#8B98A5]">
      Loading 3D plant twin…
    </div>
  ),
});

function TwinPage() {
  return (
    <div className="-mx-5">
      <div className="px-5 mb-2">
        <h1 className="text-xl font-semibold">3D Digital Twin</h1>
        <p className="text-sm text-[#8B98A5]">Inspect zones, asset health, RUL, maintenance status & open work orders</p>
      </div>
      <PlantTwin3D />
    </div>
  );
}

export default function Page() {
  return <AuthGuard><TwinPage /></AuthGuard>;
}
