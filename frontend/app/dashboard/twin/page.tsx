"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { AuthGuard } from "@/components/AuthGuard";

// three.js touches `window`, so load the 3D twin only on the client.
const PlantTwin3D = dynamic(() => import("@/components/PlantTwin3D"), {
  ssr: false,
  loading: () => (
    <div className="h-[calc(100vh-3.5rem)] grid place-items-center text-sm text-[#8B98A5]">
      Loading 3D plant twin…
    </div>
  ),
});

function TwinPage() {
  return (
    <div>
      <div className="max-w-7xl mx-auto px-5 pt-4 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold">3D Digital Twin</h1>
            <span className="text-[10px] px-2 py-0.5 rounded-full border border-[#232B35] text-[#8B98A5] bg-[#1C232C]"
              title="Physics-shaped digital twin — simulated sensors; health, RUL and work orders are live.">
              simulated plant
            </span>
          </div>
          <p className="text-sm text-[#8B98A5]">Inspect zones, asset health, RUL, maintenance status & open work orders</p>
        </div>
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-sm text-[#8B98A5] hover:text-[#E6EDF3]">
          <ArrowLeft size={14} /> Plant Overview
        </Link>
      </div>
      <PlantTwin3D />
    </div>
  );
}

export default function Page() {
  return <AuthGuard><TwinPage /></AuthGuard>;
}
