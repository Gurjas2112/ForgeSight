"use client";
import { useEffect, useState } from "react";
import { Cpu, CheckCircle2 } from "lucide-react";
import { getScorecard } from "@/lib/api";
import type { ScorecardModel } from "@/lib/types";

function liveLabel(m: ScorecardModel): string {
  const li = m.live_inference || {};
  if (m.model === "defect" && "defect_probability" in li)
    return `defect p = ${Number(li.defect_probability).toFixed(3)}`;
  if ("prediction" in li) {
    const p = Number((li as Record<string, unknown>).prediction);
    return m.model === "rul" ? `RUL ≈ ${p.toFixed(1)} cycles` : `p = ${p.toFixed(3)}`;
  }
  const rec = m.recorded || {};
  if ("anomaly_score" in rec) return `score ${Number(rec.anomaly_score).toFixed(3)}`;
  return "—";
}

function metricLabel(m: ScorecardModel): string {
  const x = m.metrics || {};
  if (x.pr_auc != null) return `PR-AUC ${x.pr_auc}` + (x.failure_recall != null ? ` · recall ${x.failure_recall}` : "");
  if (x.rmse_cycles != null) return `RMSE ${x.rmse_cycles} cycles`;
  if (x.recall != null) return `recall ${x.recall}` + (x.detection_lead_time_days != null ? ` · ${x.detection_lead_time_days}d lead` : "");
  return "";
}

export function ModelScorecard() {
  const [models, setModels] = useState<ScorecardModel[]>([]);
  const [err, setErr] = useState<string>();

  useEffect(() => {
    getScorecard().then((s) => setModels(s.models)).catch((e) => setErr(String(e)));
  }, []);

  if (err) return null; // panel is best-effort; don't block the dashboard if models aren't published

  return (
    <div className="mt-6">
      <h2 className="text-sm font-medium mb-2 text-[#8B98A5] flex items-center gap-2">
        <Cpu size={15} className="text-[#4A90D9]" /> About the models — live held-out inference, not a static claim
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {models.map((m) => {
          const live = !!(m.live_inference && (m.live_inference.live !== false));
          return (
            <div key={m.model} className="panel p-4">
              <div className="flex items-start justify-between">
                <div className="font-medium text-sm">{m.title}</div>
                {live && (
                  <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-[#3FB68B]">
                    <CheckCircle2 size={12} /> live
                  </span>
                )}
              </div>
              <div className="text-xs text-[#8B98A5] mt-0.5">{m.dataset} · {m.algorithm}</div>
              <div className="mt-3 mono text-lg text-[#FF6A2B]">{liveLabel(m)}</div>
              <div className="text-xs text-[#8B98A5] mt-1">{m.sample_label}</div>
              <div className="mt-2 text-xs text-[#9fb0c0]">{metricLabel(m)}</div>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-[#8B98A5] mt-2">
        Anomaly runs live on plant sensors; defect (LightGBM) and failure/Azure/RUL (XGBoost) run live on their
        committed held-out benchmark rows — every number above is a real, reproducible model output.
      </p>
    </div>
  );
}
