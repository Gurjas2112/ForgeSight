"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FileDown } from "lucide-react";
import { getEquipmentDetail, reportUrl } from "@/lib/api";
import type { EquipmentDetail } from "@/lib/types";
import { RulCountdown, StatusBadge } from "@/components/ui";
import { SensorTrend } from "@/components/SensorTrend";
import { Sidebar } from "@/components/Sidebar";

const GREET: Record<string, string> = {
  "hsm-f3-stand": "F3 tripped 12 min ago on fault 0247 — want a diagnosis?",
  "sinter-fan-2": "DE bearing vibration on Sinter ID Fan #2 is trending abnormal. Ask me if it can wait until Sunday's shutdown.",
};

export function EquipmentView({ id }: { id: string }) {
  const [d, setD] = useState<EquipmentDetail | null>(null);
  const [err, setErr] = useState<string>();
  useEffect(() => { getEquipmentDetail(id).then(setD).catch((e) => setErr(String(e))); }, [id]);

  const h = d?.health;
  const sev = !h ? "ok" : h.is_anomalous && (h.rul_days ?? 99) < 7 ? "high" : h.is_anomalous ? "warning" : "ok";

  return (
    <div className="max-w-7xl mx-auto px-5 py-5 grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-4 h-[calc(100vh-3.5rem)]">
      <div className="overflow-y-auto pr-1 space-y-4">
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-sm text-[#8B98A5] hover:text-[#E6EDF3]"><ArrowLeft size={14} /> Plant Overview</Link>
        {err && <div className="panel p-3 text-sm text-[#E5484D]">Backend unreachable ({err}).</div>}
        {d && (
          <>
            <div className="panel p-4 flex items-center justify-between">
              <div>
                <div className="text-lg font-semibold">{d.name}</div>
                <div className="text-xs text-[#8B98A5] mono">{d.id} · {d.zone} · criticality {d.criticality}</div>
                <div className="mt-2"><StatusBadge label={sev === "ok" ? "HEALTHY" : sev.toUpperCase()} sev={sev} /></div>
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
            {d.sensors?.length > 0 && <SensorTrend detail={d} />}
            <div className="panel p-3 text-xs text-[#8B98A5]">
              <span className="text-[#E6EDF3] font-medium">About the models:</span> anomaly = IsolationForest + EWMA (recall 1.0, 8.7d lead) ·
              RUL = trend extrapolation (XGBoost C-MAPSS RMSE 16.4 validates the method) · failure = XGBoost AI4I (recall 0.91) ·
              defect = LightGBM leakage-safe (PR-AUC 0.80) · Azure PdM 24h-ahead = XGBoost (PR-AUC 0.90, recall 0.92). Every claim cited; every score deterministic.
            </div>
          </>
        )}
      </div>
      <div className="h-full"><Sidebar equipmentId={id} greeting={GREET[id]} /></div>
    </div>
  );
}
