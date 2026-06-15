"use client";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EquipmentDetail } from "@/lib/types";

export function SensorTrend({ detail }: { detail: EquipmentDetail }) {
  const alarm = detail.thresholds?.vibration_de?.alarm;
  const data = detail.sensors.map((s) => ({
    t: new Date(s.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    v: s.vibration_de,
    anom: alarm && s.vibration_de > alarm ? s.vibration_de : null,
  }));
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium">DE bearing vibration <span className="text-[#8B98A5] mono">mm/s</span></span>
        {alarm && <span className="text-xs mono text-[#E8B931]">alarm {alarm}</span>}
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
          <defs>
            <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#4A90D9" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#4A90D9" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#232B35" vertical={false} />
          <XAxis dataKey="t" tick={{ fill: "#8B98A5", fontSize: 10 }} minTickGap={40} stroke="#232B35" />
          <YAxis tick={{ fill: "#8B98A5", fontSize: 10 }} stroke="#232B35" domain={[0, "auto"]} />
          <Tooltip contentStyle={{ background: "#0E1116", border: "1px solid #232B35", borderRadius: 8, fontSize: 12 }} />
          {alarm && <ReferenceLine y={alarm} stroke="#E8B931" strokeDasharray="4 4" label={{ value: "7.1 alarm", fill: "#E8B931", fontSize: 10, position: "insideTopRight" }} />}
          <Area type="monotone" dataKey="v" stroke="#4A90D9" fill="url(#g)" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Area type="monotone" dataKey="anom" stroke="#FF6A2B" fill="none" strokeWidth={2.5} dot={{ r: 2, fill: "#FF6A2B" }} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
