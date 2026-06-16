"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Check, FileDown } from "lucide-react";
import { getWorkOrder, patchWorkOrder, workOrderExportUrl } from "@/lib/api";
import type { WorkOrder } from "@/lib/types";
import { StatusBadge } from "@/components/ui";
import { AuthGuard } from "@/components/AuthGuard";

function WorkOrderDetail() {
  const { id } = useParams<{ id: string }>();
  const [wo, setWo] = useState<WorkOrder | null>(null);

  useEffect(() => { getWorkOrder(id).then(setWo).catch(() => {}); }, [id]);

  async function toggleStep(i: number) {
    if (!wo?.steps) return;
    const steps = wo.steps.map((s, j) => j === i ? { ...s, done: !s.done } : s);
    const updated = await patchWorkOrder(id, { steps });
    setWo(updated);
  }

  async function setStatus(status: string) {
    const updated = await patchWorkOrder(id, { status });
    setWo(updated);
  }

  if (!wo) return <div className="text-sm text-[#8B98A5]">Loading…</div>;

  return (
    <>
      <Link href="/dashboard/work-orders" className="inline-flex items-center gap-1 text-sm text-[#8B98A5] hover:text-[#E6EDF3] mb-3">
        <ArrowLeft size={14} /> Work orders
      </Link>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold">{wo.title}</h1>
          <div className="text-xs text-[#8B98A5] mono">{wo.equipment_name} · {wo.equipment_id}</div>
        </div>
        <StatusBadge label={wo.status.replace("_", " ").toUpperCase()} sev={wo.status === "completed" ? "ok" : "warning"} />
      </div>
      {wo.description && <div className="panel p-3 text-sm mb-4">{wo.description}</div>}
      <div className="flex gap-2 mb-4">
        <a href={workOrderExportUrl(id, "pdf")} target="_blank" rel="noreferrer"
          className="text-xs px-3 py-1.5 rounded bg-[#1C232C] border border-[#232B35] inline-flex items-center gap-1 hover:border-[#4A90D9]">
          <FileDown size={13} /> Export PDF
        </a>
        <a href={workOrderExportUrl(id, "json")} target="_blank" rel="noreferrer"
          className="text-xs px-3 py-1.5 rounded bg-[#1C232C] border border-[#232B35] hover:border-[#4A90D9]">Export JSON</a>
        <Link href={`/equipment/${wo.equipment_id}?prompt=${encodeURIComponent(`Status update on WO: ${wo.title}`)}`}
          className="text-xs px-3 py-1.5 rounded bg-[#4A90D9] text-white">Open in copilot</Link>
      </div>
      <h2 className="text-sm font-medium text-[#8B98A5] mb-2">Execution steps</h2>
      <div className="space-y-2 mb-4">
        {(wo.steps || []).map((s, i) => (
          <button key={i} type="button" onClick={() => toggleStep(i)}
            className={`panel p-3 w-full text-left flex items-start gap-2 ${s.done ? "opacity-60" : ""}`}>
            <span className={s.done ? "text-[#3FB68B]" : "text-[#8B98A5]"}><Check size={16} /></span>
            <span className="text-sm">{s.text}{s.safety && <span className="text-[#E8B931] ml-1">· SAFETY</span>}</span>
          </button>
        ))}
      </div>
      <div className="flex gap-2">
        {wo.status !== "in_progress" && wo.status !== "completed" && (
          <button onClick={() => setStatus("in_progress")} className="text-xs px-3 py-1.5 rounded bg-[#E8B931] text-black">Start work</button>
        )}
        {wo.status !== "completed" && (
          <button onClick={() => setStatus("completed")} className="text-xs px-3 py-1.5 rounded bg-[#3FB68B] text-black">Mark complete</button>
        )}
      </div>
    </>
  );
}

export default function Page() {
  return <AuthGuard><WorkOrderDetail /></AuthGuard>;
}
