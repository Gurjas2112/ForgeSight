"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { FileDown } from "lucide-react";
import { getWorkOrders, workOrderExportUrl } from "@/lib/api";
import type { WorkOrder } from "@/lib/types";
import { StatusBadge } from "@/components/ui";
import { AuthGuard } from "@/components/AuthGuard";

const STATUS_COL: Record<string, string> = {
  open: "warning", in_progress: "high", completed: "ok", draft: "info", cancelled: "info",
};

function WorkOrdersList() {
  const [wos, setWos] = useState<WorkOrder[]>([]);
  const [filter, setFilter] = useState<string>("");

  useEffect(() => {
    getWorkOrders(filter ? { status: filter } : undefined).then(setWos).catch(() => {});
  }, [filter]);

  return (
    <>
      <h1 className="text-xl font-semibold mb-1">Work orders</h1>
      <p className="text-sm text-[#8B98A5] mb-4">Status tracking, export, and maintenance execution flow.</p>
      <div className="flex gap-2 mb-4">
        {["", "open", "in_progress", "completed"].map((s) => (
          <button key={s || "all"} type="button" onClick={() => setFilter(s)}
            className={`text-xs px-2.5 py-1 rounded border ${filter === s ? "border-[#4A90D9] text-[#4A90D9]" : "border-[#232B35] text-[#8B98A5]"}`}>
            {s || "all"}
          </button>
        ))}
      </div>
      <div className="space-y-2">
        {wos.map((wo) => (
          <Link key={wo.id} href={`/dashboard/work-orders/${wo.id}`} className="panel p-4 block hover:border-[#4A90D9]">
            <div className="flex items-start justify-between">
              <div>
                <div className="font-medium">{wo.title}</div>
                <div className="text-xs text-[#8B98A5] mono mt-0.5">{wo.equipment_name || wo.equipment_id} · priority {wo.priority ?? "—"}</div>
              </div>
              <StatusBadge label={wo.status.replace("_", " ").toUpperCase()} sev={STATUS_COL[wo.status] || "info"} />
            </div>
            <div className="flex gap-2 mt-2">
              <a href={workOrderExportUrl(wo.id, "pdf")} onClick={(e) => e.stopPropagation()} target="_blank" rel="noreferrer"
                className="text-[11px] inline-flex items-center gap-1 text-[#9fb0c0] hover:text-[#4A90D9]"><FileDown size={12} /> PDF</a>
              <a href={workOrderExportUrl(wo.id, "json")} onClick={(e) => e.stopPropagation()} target="_blank" rel="noreferrer"
                className="text-[11px] text-[#9fb0c0] hover:text-[#4A90D9]">JSON</a>
            </div>
          </Link>
        ))}
        {wos.length === 0 && <div className="panel p-4 text-sm text-[#8B98A5]">No work orders.</div>}
      </div>
    </>
  );
}

export default function Page() {
  return <AuthGuard><WorkOrdersList /></AuthGuard>;
}
