"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getEquipment, getReliability } from "@/lib/api";
import type { Equipment, ReliabilityData } from "@/lib/types";
import { AuthGuard } from "@/components/AuthGuard";

function ReliabilityGraph({ graph }: { graph: ReliabilityData["graph"] }) {
  if (!graph) return null;
  const byType: Record<string, string> = { equipment: "#4A90D9", sensor: "#3FB68B", spare: "#E8B931", incident: "#FF6A2B" };
  return (
    <div className="panel p-4">
      <div className="text-sm font-medium mb-3">Relationship graph</div>
      <div className="flex flex-wrap gap-2">
        {graph.nodes.map((n) => (
          <span key={n.id} className="text-xs px-2 py-1 rounded border border-[#232B35]"
            style={{ borderColor: byType[n.type] || "#232B35", color: byType[n.type] || "#8B98A5" }}>
            {n.type}: {n.label}
          </span>
        ))}
      </div>
      <div className="mt-3 text-[10px] text-[#8B98A5] space-y-0.5 max-h-32 overflow-y-auto">
        {graph.edges.map((e, i) => (
          <div key={i}>{e.source} → {e.target} ({e.relation})</div>
        ))}
      </div>
    </div>
  );
}

function ReliabilityPage() {
  const [eq, setEq] = useState<Equipment[]>([]);
  const [sel, setSel] = useState("");
  const [data, setData] = useState<ReliabilityData | null>(null);

  useEffect(() => {
    getEquipment().then((list) => { setEq(list); if (list[0]) setSel(list[0].id); }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!sel) return;
    getReliability(sel).then(setData).catch(() => setData(null));
  }, [sel]);

  const trendData = (data?.trend_analysis || []).map((t) => ({ t: t.ts.slice(5, 10), v: t.vibration_avg }));

  return (
    <>
      <h1 className="text-xl font-semibold mb-1">Predictive reliability</h1>
      <p className="text-sm text-[#8B98A5] mb-4">Failure probability, RUL forecast, trend analysis, and relationship graph.</p>
      <select value={sel} onChange={(e) => setSel(e.target.value)}
        className="mb-4 bg-[#0E1116] border border-[#232B35] rounded-lg px-3 py-2 text-sm">
        {eq.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
      </select>
      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <div className="panel p-3"><div className="text-xs text-[#8B98A5]">RUL</div><div className="mono text-xl text-[#FF6A2B]">{data.rul_days ?? "—"}d</div></div>
            <div className="panel p-3"><div className="text-xs text-[#8B98A5]">Failure prob.</div><div className="mono text-xl">{(data.failure_probability ?? 0) * 100}%</div></div>
            <div className="panel p-3"><div className="text-xs text-[#8B98A5]">Anomaly</div><div className="mono text-xl">{data.anomaly_score ?? "—"}</div></div>
            <div className="panel p-3"><div className="text-xs text-[#8B98A5]">RUL band</div><div className="mono text-sm">{data.rul_band?.join("–") ?? "—"} d</div></div>
          </div>
          {trendData.length > 0 && (
            <div className="panel p-4 mb-4">
              <div className="text-sm font-medium mb-2">Trend analysis</div>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={trendData}>
                  <CartesianGrid stroke="#232B35" vertical={false} />
                  <XAxis dataKey="t" tick={{ fill: "#8B98A5", fontSize: 10 }} />
                  <YAxis tick={{ fill: "#8B98A5", fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: "#0E1116", border: "1px solid #232B35", fontSize: 12 }} />
                  <Line type="monotone" dataKey="v" stroke="#4A90D9" strokeWidth={2} dot={false} name="vibration avg" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <ReliabilityGraph graph={data.graph} />
          <Link href={`/equipment/${sel}?prompt=${encodeURIComponent(`Reliability action plan for ${data.name} — RUL ${data.rul_days}d`)}`}
            className="mt-4 inline-block text-sm px-4 py-2 rounded bg-[#4A90D9] text-white">
            Act on this asset
          </Link>
        </>
      )}
    </>
  );
}

export default function Page() {
  return <AuthGuard><ReliabilityPage /></AuthGuard>;
}
