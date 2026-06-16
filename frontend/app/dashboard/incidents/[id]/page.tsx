"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getIncident, getIncidentLessons, getIncidentReplay } from "@/lib/api";
import type { Incident } from "@/lib/types";
import { AuthGuard } from "@/components/AuthGuard";

function IncidentDetail() {
  const { id } = useParams<{ id: string }>();
  const [inc, setInc] = useState<Incident | null>(null);
  const [sensors, setSensors] = useState<{ ts: string; vibration_de: number }[]>([]);
  const [lessons, setLessons] = useState<Incident[]>([]);

  useEffect(() => {
    getIncident(id).then(setInc).catch(() => {});
    getIncidentReplay(id).then((r) => setSensors(r.sensors)).catch(() => {});
    getIncidentLessons(id).then((r) => setLessons(r.lessons)).catch(() => {});
  }, [id]);

  const chartData = sensors.map((s) => ({
    t: new Date(s.ts).toLocaleDateString([], { month: "short", day: "numeric" }),
    v: s.vibration_de,
  }));

  if (!inc) return <div className="text-sm text-[#8B98A5]">Loading…</div>;

  return (
    <>
      <Link href="/dashboard/incidents" className="inline-flex items-center gap-1 text-sm text-[#8B98A5] hover:text-[#E6EDF3] mb-3">
        <ArrowLeft size={14} /> Incidents
      </Link>
      <h1 className="text-xl font-semibold">{inc.fault_code || inc.id}</h1>
      <div className="text-xs text-[#8B98A5] mb-4">{inc.equipment_name} · {inc.occurred_at} · impact {inc.production_impact_label}</div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        {(inc.failure_progression || []).map((s) => (
          <div key={s.stage} className="panel p-3">
            <div className="text-xs text-[#8B98A5]">{s.stage}</div>
            <div className="text-sm mt-1">{s.detail || "—"}</div>
          </div>
        ))}
      </div>

      {chartData.length > 0 && (
        <div className="panel p-4 mb-4">
          <div className="text-sm font-medium mb-2">Sensor replay (±7 days)</div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData}>
              <CartesianGrid stroke="#232B35" vertical={false} />
              <XAxis dataKey="t" tick={{ fill: "#8B98A5", fontSize: 10 }} />
              <YAxis tick={{ fill: "#8B98A5", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "#0E1116", border: "1px solid #232B35", fontSize: 12 }} />
              <Area type="monotone" dataKey="v" stroke="#FF6A2B" fill="#FF6A2B33" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="panel p-4 mb-4">
        <div className="text-sm font-medium mb-2">Lessons learned (similar verified failures)</div>
        {lessons.length === 0 && <div className="text-xs text-[#8B98A5]">No similar verified incidents.</div>}
        {lessons.map((l) => (
          <div key={l.id} className="text-sm border-t border-[#232B35] pt-2 mt-2">
            <span className="mono text-[#4A90D9]">{l.id}</span> — {l.root_cause}: {l.resolution}
          </div>
        ))}
      </div>

      <Link href={`/equipment/${inc.equipment_id}?prompt=${encodeURIComponent(`Similar failure to ${inc.fault_code}? What should we watch for?`)}`}
        className="text-sm px-4 py-2 rounded bg-[#4A90D9] text-white inline-block">
        Investigate with copilot
      </Link>
    </>
  );
}

export default function Page() {
  return <AuthGuard><IncidentDetail /></AuthGuard>;
}
