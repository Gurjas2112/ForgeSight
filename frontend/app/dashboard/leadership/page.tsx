"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getLeadershipROI } from "@/lib/api";
import type { LeadershipROI } from "@/lib/types";
import { AuthGuard } from "@/components/AuthGuard";

function LeadershipPage() {
  const [roi, setRoi] = useState<LeadershipROI | null>(null);
  useEffect(() => { getLeadershipROI().then(setRoi).catch(() => {}); }, []);

  if (!roi) return <div className="text-sm text-[#8B98A5]">Loading…</div>;

  return (
    <>
      <h1 className="text-xl font-semibold mb-1">Leadership review</h1>
      <p className="text-sm text-[#8B98A5] mb-4">Shutdown cost, potential failure cost, expected savings, ROI, and recommended actions.</p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <div className="panel p-3"><div className="text-xs text-[#8B98A5]">Shutdown cost</div><div className="mono text-lg">{roi.shutdown_cost_label}</div></div>
        <div className="panel p-3"><div className="text-xs text-[#8B98A5]">Potential failure</div><div className="mono text-lg text-[#FF6A2B]">{roi.potential_failure_cost_label}</div></div>
        <div className="panel p-3"><div className="text-xs text-[#8B98A5]">Expected savings</div><div className="mono text-lg text-[#3FB68B]">{roi.expected_savings_label}</div></div>
        <div className="panel p-3"><div className="text-xs text-[#8B98A5]">Top action</div>
          <div className="text-sm mt-1">{roi.top_recommendation?.recommended_action ?? "—"}</div></div>
      </div>
      <div className="space-y-2">
        {roi.recommendations.map((r) => (
          <div key={r.equipment_id} className="panel p-4 flex items-center justify-between gap-4">
            <div>
              <div className="font-medium">{r.name}</div>
              <div className="text-xs text-[#8B98A5]">{r.zone} · ROI {r.roi}x · confidence {r.confidence}</div>
              <div className="text-xs text-[#9fb0c0] mt-1">Save {r.expected_savings_label} vs failure {r.potential_failure_cost_label}</div>
            </div>
            <Link href={`/equipment/${r.equipment_id}?prompt=${encodeURIComponent(r.copilot_prompt)}`}
              className="text-xs px-3 py-2 rounded bg-[#FF6A2B] text-black font-medium whitespace-nowrap">
              Investigate
            </Link>
          </div>
        ))}
        {roi.recommendations.length === 0 && <div className="panel p-4 text-sm text-[#8B98A5]">No at-risk assets requiring leadership action.</div>}
      </div>
      <p className="text-[10px] text-[#8B98A5] mt-4">Cost assumptions: {JSON.stringify(roi.assumptions)}</p>
    </>
  );
}

export default function Page() {
  return <AuthGuard><LeadershipPage /></AuthGuard>;
}
