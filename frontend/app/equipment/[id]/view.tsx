"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Bot, FileDown, Wrench } from "lucide-react";
import { getEquipmentDetail, getLogbook, postHandover, reportUrl, getEquipmentContext } from "@/lib/api";
import type { EquipmentContext, EquipmentDetail, LogbookEntry } from "@/lib/types";
import { RulCountdown, StatusBadge } from "@/components/ui";
import { SensorTrend } from "@/components/SensorTrend";
import { Sidebar } from "@/components/Sidebar";

const GREET: Record<string, string> = {
  "hsm-f3-stand": "F3 tripped 12 min ago on fault 0247 — want a diagnosis?",
  "sinter-fan-2": "DE bearing vibration on Sinter ID Fan #2 is trending abnormal. Ask me if it can wait until Sunday's shutdown.",
};

export function EquipmentView({ id }: { id: string }) {
  const searchParams = useSearchParams();
  const prompt = searchParams.get("prompt") || undefined;
  const [d, setD] = useState<EquipmentDetail | null>(null);
  const [ctx, setCtx] = useState<EquipmentContext | null>(null);
  const [logbook, setLogbook] = useState<LogbookEntry[]>([]);
  const [tab, setTab] = useState<"sensors" | "maintenance">("sensors");
  const [handover, setHandover] = useState("");
  const [err, setErr] = useState<string>();

  useEffect(() => {
    getEquipmentDetail(id).then(setD).catch((e) => setErr(String(e)));
    getEquipmentContext(id).then(setCtx).catch(() => {});
    getLogbook(id).then(setLogbook).catch(() => {});
  }, [id]);

  const h = d?.health;
  const sev = !h ? "ok" : h.is_anomalous && (h.rul_days ?? 99) < 7 ? "high" : h.is_anomalous ? "warning" : "ok";
  const investigatePrompt = prompt || (ctx
    ? `Investigate ${ctx.name}: anomaly ${ctx.anomaly_score}, RUL ${ctx.rul_days}d, ${ctx.open_alerts.length} open alerts`
    : undefined);

  async function submitHandover() {
    if (!handover.trim()) return;
    await postHandover({
      equipment_id: id,
      notes: handover,
      open_work_orders: ctx?.open_work_orders.map((w) => w.id),
      risk_context: { anomaly: ctx?.anomaly_score, rul_days: ctx?.rul_days },
    });
    setHandover("");
    getLogbook(id).then(setLogbook);
  }

  return (
    <div className="max-w-7xl mx-auto px-5 py-5 grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-4 h-[calc(100vh-3.5rem)]">
      <div className="overflow-y-auto pr-1 space-y-4">
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-sm text-[#8B98A5] hover:text-[#E6EDF3]"><ArrowLeft size={14} /> Plant Overview</Link>
        {err && <div className="panel p-3 text-sm text-[#E5484D]">Backend unreachable ({err}).</div>}

        {ctx && (
          <div className="panel p-3 grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
            <div><span className="text-[#8B98A5]">Risk</span><div className="mono text-[#FF6A2B]">{ctx.downtime_at_risk_label}</div></div>
            <div><span className="text-[#8B98A5]">Alerts</span><div>{ctx.open_alerts.length}</div></div>
            <div><span className="text-[#8B98A5]">Work orders</span><div>{ctx.open_work_orders.length}</div></div>
            <div><span className="text-[#8B98A5]">Spares</span><div>{ctx.spares[0]?.procurement_action?.replace("_", " ") ?? "—"}</div></div>
            <div className="col-span-2 md:col-span-1">
              <Link href={`/equipment/${id}?prompt=${encodeURIComponent(investigatePrompt || "")}`}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-[#4A90D9] text-white w-full justify-center">
                <Bot size={12} /> Start AI investigation
              </Link>
            </div>
          </div>
        )}

        {d && (
          <>
            <div className="panel p-4 flex items-center justify-between">
              <div>
                <div className="text-lg font-semibold">{d.name}</div>
                <div className="text-xs text-[#8B98A5] mono">{d.id} · {d.zone} · criticality {d.criticality}</div>
                <div className="mt-2 flex items-center gap-2 flex-wrap">
                  <StatusBadge label={sev === "ok" ? "HEALTHY" : sev.toUpperCase()} sev={sev} />
                  {ctx?.open_work_orders.slice(0, 2).map((w) => (
                    <Link key={w.id} href={`/dashboard/work-orders/${w.id}`} className="text-[10px] text-[#4A90D9] hover:underline">WO: {w.title.slice(0, 30)}…</Link>
                  ))}
                  <Link href={`/dashboard/incidents?equipment=${id}`} className="text-[10px] text-[#8B98A5] hover:text-[#4A90D9]">Incidents</Link>
                  <Link href={`/dashboard/spares?equipment=${id}`} className="text-[10px] text-[#8B98A5] hover:text-[#4A90D9]">Spares</Link>
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                {h?.rul_days != null && <RulCountdown days={h.rul_days} />}
                <a href={reportUrl(d.id)} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-[#1C232C] border border-[#232B35] text-[#9fb0c0] hover:border-[#4A90D9]">
                  <FileDown size={13} /> Alert report (PDF)
                </a>
              </div>
            </div>
            {h && (
              <div className="grid grid-cols-3 gap-3">
                <div className="panel p-3"><div className="text-xs text-[#8B98A5]">Anomaly score</div><div className="mono text-xl" style={{ color: h.is_anomalous ? "#FF6A2B" : "#3FB68B" }}>{h.anomaly_score}</div></div>
                <div className="panel p-3"><div className="text-xs text-[#8B98A5]">Contributing</div><div className="text-sm mt-1">{(h.contributing_sensors || []).join(", ") || "—"}</div></div>
                <div className="panel p-3"><div className="text-xs text-[#8B98A5]">RUL band</div><div className="mono text-sm mt-1">{h.rul_band?.band ? `${h.rul_band.band[0]}–${h.rul_band.band[1]} d` : "—"}</div></div>
              </div>
            )}

            <div className="flex gap-2 border-b border-[#232B35]">
              <button type="button" onClick={() => setTab("sensors")}
                className={`text-sm px-3 py-2 border-b-2 ${tab === "sensors" ? "border-[#4A90D9] text-[#E6EDF3]" : "border-transparent text-[#8B98A5]"}`}>Sensors</button>
              <button type="button" onClick={() => setTab("maintenance")}
                className={`text-sm px-3 py-2 border-b-2 inline-flex items-center gap-1 ${tab === "maintenance" ? "border-[#4A90D9] text-[#E6EDF3]" : "border-transparent text-[#8B98A5]"}`}>
                <Wrench size={14} /> Maintenance
              </button>
            </div>

            {tab === "sensors" && d.sensors?.length > 0 && <SensorTrend detail={d} />}

            {tab === "maintenance" && (
              <div className="space-y-3">
                <div className="panel p-4">
                  <div className="text-sm font-medium mb-2">Shift handover</div>
                  <textarea value={handover} onChange={(e) => setHandover(e.target.value)} rows={3} placeholder="Handover notes, open risks, pending actions…"
                    className="w-full bg-[#0E1116] border border-[#232B35] rounded-lg px-3 py-2 text-sm outline-none focus:border-[#4A90D9]" />
                  <button type="button" onClick={submitHandover} className="mt-2 text-xs px-3 py-1.5 rounded bg-[#4A90D9] text-white">Save handover</button>
                </div>
                <div className="panel p-4">
                  <div className="text-sm font-medium mb-2">Logbook & reliability corrections</div>
                  {logbook.length === 0 && <div className="text-xs text-[#8B98A5]">No entries yet. Use copilot feedback (&quot;This fixed it&quot;) to record verified fixes.</div>}
                  {logbook.map((e) => (
                    <div key={e.id} className="text-xs border-t border-[#232B35] pt-2 mt-2">
                      <span className="text-[#8B98A5]">{e.created_at.slice(0, 16)}</span> · {e.entry_type}
                      <pre className="text-[#c3ced9] mt-1 whitespace-pre-wrap">{JSON.stringify(e.content, null, 2)}</pre>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
      <div className="h-full"><Sidebar equipmentId={id} greeting={GREET[id]} initialPrompt={investigatePrompt} /></div>
    </div>
  );
}
