"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { getAlerts, getEquipment } from "@/lib/api";
import type { Alert, Equipment } from "@/lib/types";
import { StatusBadge } from "@/components/ui";

function tileState(e: Equipment): { sev: string; label: string } {
  if (e.id === "hsm-f3-stand") return { sev: "critical", label: "TRIPPED · HSM-F3-VFD-0247" };
  if (e.is_anomalous && (e.rul_days ?? 99) < 7) return { sev: "high", label: `EARLY WARNING · RUL ≈ ${e.rul_days}d` };
  if (e.is_anomalous) return { sev: "warning", label: "ABNORMAL TREND" };
  return { sev: "ok", label: "HEALTHY" };
}

export default function Overview() {
  const [eq, setEq] = useState<Equipment[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [err, setErr] = useState<string>();

  useEffect(() => {
    getEquipment().then(setEq).catch((e) => setErr(String(e)));
    getAlerts().then(setAlerts).catch(() => {});
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-5 py-6">
      <div className="flex items-end justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold">Plant Overview</h1>
          <p className="text-sm text-[#8B98A5]">6 critical assets · governed multi-agent decision support</p>
        </div>
        <div className="flex gap-6 text-right">
          <div><div className="mono text-2xl font-semibold text-[#3FB68B]">92%</div><div className="text-xs text-[#8B98A5]">availability</div></div>
          <div><div className="mono text-2xl font-semibold text-[#E8B931]">{alerts.length}</div><div className="text-xs text-[#8B98A5]">open alerts</div></div>
          <div><div className="mono text-2xl font-semibold text-[#FF6A2B]">₹18L</div><div className="text-xs text-[#8B98A5]">downtime at risk</div></div>
        </div>
      </div>

      {err && <div className="panel p-3 mb-4 text-sm text-[#E5484D]">Backend unreachable ({err}). Start: <span className="mono">uvicorn backend.server:app --port 8000</span></div>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {eq.map((e) => {
          const st = tileState(e);
          const crit = st.sev === "critical";
          return (
            <Link key={e.id} href={`/equipment/${e.id}`}
              className={`panel p-4 hover:border-[#4A90D9] transition-colors group ${crit ? "pulse-crit border-[#E5484D]" : ""}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-medium">{e.name}</div>
                  <div className="text-xs text-[#8B98A5]">{e.zone} · criticality {e.criticality}</div>
                </div>
                <StatusBadge label={st.sev === "ok" ? "OK" : st.sev.toUpperCase()} sev={st.sev} />
              </div>
              <div className={`mt-3 text-sm mono ${crit ? "text-[#FF6A2B]" : st.sev === "ok" ? "text-[#3FB68B]" : "text-[#E8B931]"}`}>{st.label}</div>
              <div className="mt-3 flex items-center justify-between text-xs text-[#8B98A5]">
                <span>{e.anomaly_score != null ? `anomaly ${e.anomaly_score}` : "—"}{e.rul_days != null ? ` · RUL ${e.rul_days}d` : ""}</span>
                <ArrowRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </Link>
          );
        })}
      </div>

      {alerts.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-medium mb-2 text-[#8B98A5]">Live alert feed</h2>
          <div className="space-y-1.5">
            {alerts.map((a) => (
              <Link key={a.id} href={`/equipment/${a.equipment_id}`} className="panel p-3 flex items-center gap-2 text-sm hover:border-[#4A90D9]">
                <AlertTriangle size={15} className="text-[#FF6A2B]" />
                <span className="flex-1">{a.title}</span>
                <StatusBadge label={a.severity.toUpperCase()} sev={a.severity} />
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
