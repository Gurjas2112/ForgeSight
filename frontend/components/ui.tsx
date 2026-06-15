"use client";
import { FileText, Clock, TrendingUp, Cog, Database, Bot } from "lucide-react";

const SEV: Record<string, string> = {
  critical: "#E5484D", high: "#E5484D", warning: "#E8B931", medium: "#E8B931",
  low: "#3FB68B", info: "#4A90D9", ok: "#3FB68B",
};

export function StatusBadge({ label, sev = "ok" }: { label: string; sev?: string }) {
  const c = SEV[sev] ?? "#3FB68B";
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
      style={{ background: `${c}1a`, color: c, border: `1px solid ${c}55` }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: c }} />{label}
    </span>
  );
}

export function RiskPill({ level }: { level: string }) {
  return <StatusBadge label={level.toUpperCase()} sev={level} />;
}

export function ConfidencePill({ value }: { value: string }) {
  const sev = value === "High" ? "ok" : value === "Medium" ? "warning" : "high";
  return <StatusBadge label={`${value} confidence`} sev={sev} />;
}

export function RulCountdown({ days }: { days: number }) {
  const sev = days < 7 ? "high" : days < 21 ? "warning" : "ok";
  const c = SEV[sev];
  return (
    <div className="flex flex-col">
      <span className="text-xs text-[#8B98A5]">Est. RUL</span>
      <span className="mono text-2xl font-semibold" style={{ color: c }}>≈ {days}<span className="text-base ml-1">d</span></span>
    </div>
  );
}

export function AgentByline({ agent, kind }: { agent: string; kind?: string }) {
  const label = agent.replace(/_/g, " ").replace(/\bagent\b/i, "Agent");
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[#8B98A5]">
      <Bot size={13} className="text-[#4A90D9]" />
      <span className="capitalize">{label}</span>
      {kind && <span className="px-1.5 py-0.5 rounded bg-[#1C232C] text-[10px] uppercase tracking-wide">{kind}</span>}
    </span>
  );
}

const CITE_ICON: Record<string, React.ReactNode> = {
  sop: <FileText size={12} />, manual: <FileText size={12} />, history: <Clock size={12} />,
  trend: <TrendingUp size={12} />, priority_matrix: <Cog size={12} />,
  spares_record: <Database size={12} />, model_output: <Cog size={12} />,
};

export function EvidenceChip({ kind, label, onClick }: { kind: string; label: string; onClick?: () => void }) {
  return (
    <button onClick={onClick}
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs mono
                 bg-[#1C232C] border border-[#232B35] text-[#9fb0c0]
                 hover:border-[#4A90D9] hover:text-[#E6EDF3] transition-colors">
      <span className="text-[#4A90D9]">{CITE_ICON[kind] ?? <FileText size={12} />}</span>
      {label}
    </button>
  );
}
