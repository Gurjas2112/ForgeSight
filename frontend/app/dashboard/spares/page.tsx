"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getInventoryOptimizer, getSpares } from "@/lib/api";
import type { OptimizerResult, SpareCatalogItem } from "@/lib/types";
import { StatusBadge } from "@/components/ui";
import { AuthGuard } from "@/components/AuthGuard";

function SparesPage() {
  const [catalog, setCatalog] = useState<SpareCatalogItem[]>([]);
  const [optimizer, setOptimizer] = useState<OptimizerResult | null>(null);

  useEffect(() => {
    getSpares().then(setCatalog).catch(() => {});
    getInventoryOptimizer().then(setOptimizer).catch(() => {});
  }, []);

  return (
    <>
      <h1 className="text-xl font-semibold mb-1">Spares & inventory</h1>
      <p className="text-sm text-[#8B98A5] mb-4">Catalog cards with stock, cost, lead time, and inventory optimizer for shortage risk.</p>

      {optimizer && (
        <div className="panel p-4 mb-5">
          <div className="text-sm font-medium mb-2">Inventory optimizer</div>
          <div className="flex gap-6 mb-3">
            <div><div className="mono text-xl text-[#FF6A2B]">{optimizer.total_production_exposure_label}</div>
              <div className="text-xs text-[#8B98A5]">production exposure</div></div>
            <div><div className="mono text-xl text-[#E8B931]">{optimizer.at_risk_parts}</div>
              <div className="text-xs text-[#8B98A5]">parts at shortage risk</div></div>
          </div>
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {optimizer.items.filter((i) => i.shortage_risk).slice(0, 6).map((i) => (
              <div key={i.part_no} className="text-xs flex justify-between panel p-2">
                <span>{i.part_no} · {i.equipment_name}</span>
                <span className="text-[#FF6A2B]">{i.production_exposure_label} · {i.recommended_action.replace("_", " ")}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {catalog.map((s) => (
          <div key={s.part_no} className="panel p-4">
            <div className="font-medium mono text-sm">{s.part_no}</div>
            <div className="text-xs text-[#8B98A5] mt-0.5">{s.description}</div>
            <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
              <div><span className="text-[#8B98A5]">Stock</span><div className="mono">{s.stock_qty}</div></div>
              <div><span className="text-[#8B98A5]">Lead time</span><div className="mono">{s.lead_time_days}d</div></div>
              <div><span className="text-[#8B98A5]">Cost</span><div className="mono">₹{(s.unit_cost_inr / 1000).toFixed(0)}K</div></div>
              <div><span className="text-[#8B98A5]">Asset</span><div>{s.equipment_name || s.equipment_id}</div></div>
            </div>
            <div className="mt-2">
              <StatusBadge label={(s.procurement_action || "monitor").replace("_", " ").toUpperCase()}
                sev={s.procurement_action === "order_now" ? "critical" : s.procurement_action === "reserve_now" ? "high" : "ok"} />
            </div>
            <Link href={`/equipment/${s.equipment_id}?prompt=${encodeURIComponent(`Reserve or order spare ${s.part_no}`)}`}
              className="mt-3 block text-center text-xs px-3 py-1.5 rounded bg-[#4A90D9] text-white">
              Request PO via copilot
            </Link>
          </div>
        ))}
      </div>
    </>
  );
}

export default function Page() {
  return <AuthGuard><SparesPage /></AuthGuard>;
}
