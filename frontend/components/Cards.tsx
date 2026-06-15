"use client";
import { ShieldAlert, AlertTriangle, CheckCircle2, Package } from "lucide-react";
import type { Card } from "@/lib/types";
import { AgentByline, ConfidencePill, EvidenceChip, RiskPill, StatusBadge } from "./ui";

function EvidenceTrail({ refs, onOpen }: { refs?: string[]; onOpen: (r: string) => void }) {
  if (!refs?.length) return null;
  const kindFor = (r: string) => r.startsWith("BR-") ? "history" : r.startsWith("SOP") || r.startsWith("SNT") || r.includes("SOP") ? "sop"
    : r.includes("matrix") ? "priority_matrix" : r.includes("trend") ? "trend" : r.match(/^[A-Z]+-\d/) ? "spares_record" : "model_output";
  return (
    <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-[#232B35]">
      <span className="text-[10px] uppercase tracking-wide text-[#8B98A5] self-center mr-1">Evidence</span>
      {refs.map((r) => <EvidenceChip key={r} kind={kindFor(r)} label={r} onClick={() => onOpen(r)} />)}
    </div>
  );
}

const Shell = ({ children, byline, tag }: { children: React.ReactNode; byline: string; tag?: string }) => (
  <div className="panel p-4 slidein">
    <div className="flex items-center justify-between mb-2">
      <AgentByline agent={byline} kind={tag} />
    </div>
    {children}
  </div>
);

export function CardView({ card, onOpenEvidence }: { card: Card; onOpenEvidence: (r: string) => void }) {
  const t = card.card_type;

  if (t === "diagnosis")
    return (
      <Shell byline="diagnostic_agent" tag="AI-assisted">
        <div className="flex items-center gap-2 mb-1">
          <ShieldAlert size={16} className="text-[#FF6A2B]" />
          <span className="mono font-semibold">{card.fault}</span>
          {card.confidence && <ConfidencePill value={card.confidence} />}
          {card.served_from_cache && <StatusBadge label="cached" sev="info" />}
        </div>
        <p className="text-sm text-[#c3ced9] mb-3">{card.summary}</p>
        <ol className="space-y-1.5">
          {card.root_causes?.map((rc) => (
            <li key={rc.rank} className="flex gap-2 text-sm">
              <span className="mono text-[#4A90D9]">{rc.rank}.</span>
              <span className="flex-1">{rc.cause}
                <span className="ml-2 text-xs text-[#8B98A5]">[{rc.confidence}]</span></span>
            </li>
          ))}
        </ol>
        {card.recommended_next && <p className="text-sm mt-3 text-[#9fb0c0]">→ {card.recommended_next}</p>}
        <EvidenceTrail refs={card.citation_refs} onOpen={onOpenEvidence} />
      </Shell>
    );

  if (t === "checklist")
    return (
      <Shell byline="diagnostic_agent" tag="SOP">
        <div className="font-semibold mb-2">{card.title}</div>
        <ol className="space-y-1.5">
          {card.steps?.map((s, i) => (
            <li key={i} className={`flex gap-2 text-sm p-2 rounded ${s.safety ? "bg-[#E8B93114] border border-[#E8B93155]" : ""}`}>
              {s.safety ? <AlertTriangle size={15} className="text-[#E8B931] mt-0.5 shrink-0" /> : <span className="mono text-[#4A90D9]">{i + 1}.</span>}
              <span className="flex-1">{s.text}{s.expected && <span className="ml-2 mono text-xs text-[#3FB68B]">({s.expected})</span>}</span>
            </li>
          ))}
        </ol>
        <EvidenceTrail refs={card.citation_refs} onOpen={onOpenEvidence} />
      </Shell>
    );

  if (t === "wait_assessment") {
    const v = card.verdict;
    const sev = v === "yes" ? "ok" : v === "yes_with_conditions" ? "warning" : "high";
    return (
      <Shell byline="reliability_agent" tag="3-agent fan-out">
        <div className="flex items-center gap-2 mb-2">
          <StatusBadge label={(v || "").replace(/_/g, " ").toUpperCase() || "ASSESSMENT"} sev={sev} />
          {card.rul_days != null && <span className="mono text-sm text-[#8B98A5]">RUL ≈ {card.rul_days}d</span>}
        </div>
        <p className="text-sm text-[#c3ced9]">{card.summary}</p>
        {card.monitoring_plan && <p className="text-sm mt-2 text-[#9fb0c0]">Monitoring: {card.monitoring_plan}</p>}
        {card.procurement_callout && <p className="text-sm mt-2 text-[#FF6A2B]">⚠ {card.procurement_callout}</p>}
        <EvidenceTrail refs={card.citation_refs} onOpen={onOpenEvidence} />
      </Shell>
    );
  }

  if (t === "priority")
    return (
      <Shell byline="supervisor_agent" tag="rule-based score">
        <div className="flex items-center gap-2 mb-2">
          <span className="mono text-2xl font-semibold text-[#4A90D9]">{card.priority_score}</span>
          <span className="text-xs text-[#8B98A5]">/100 priority</span>
        </div>
        <div className="space-y-1">
          {card.factors?.map((f) => (
            <div key={f.name} className="flex items-center gap-2 text-xs">
              <span className="w-28 text-[#8B98A5] capitalize">{f.name.replace(/_/g, " ")}</span>
              <div className="flex-1 h-1.5 rounded bg-[#1C232C]"><div className="h-full rounded bg-[#4A90D9]" style={{ width: `${f.contribution}%` }} /></div>
              <span className="mono w-10 text-right">{f.contribution}</span>
            </div>
          ))}
        </div>
        <p className="text-xs text-[#8B98A5] mt-2">{card.rationale}</p>
        <EvidenceTrail refs={card.citation_refs} onOpen={onOpenEvidence} />
      </Shell>
    );

  if (t === "spares")
    return (
      <Shell byline="planner_agent" tag="procurement">
        <div className="flex items-center gap-2 mb-1">
          <Package size={16} className="text-[#4A90D9]" />
          <span className="mono font-semibold">{card.part_no}</span>
          <StatusBadge label={`${card.stock_qty ?? 0} in stock`} sev={(card.stock_qty ?? 0) > 0 ? "ok" : "high"} />
          <span className="mono text-xs text-[#8B98A5]">lead {card.lead_time_days}d</span>
        </div>
        {card.procurement_note && <p className="text-sm text-[#c3ced9]">{card.procurement_note}</p>}
        {card.proposal && <p className="text-sm mt-2 text-[#FF6A2B]">{card.proposal}</p>}
        <EvidenceTrail refs={card.citation_refs} onOpen={onOpenEvidence} />
      </Shell>
    );

  if (t === "rul" || t === "risk")
    return (
      <Shell byline="reliability_agent" tag="ML">
        {card.risk_level && <RiskPill level={card.risk_level} />}
        {card.rul_days != null && <div className="mono text-xl font-semibold text-[#FF6A2B] mt-1">RUL ≈ {card.rul_days}d</div>}
        <p className="text-sm text-[#c3ced9] mt-1">{card.justification || card.note || card.summary}</p>
        <EvidenceTrail refs={card.citation_refs} onOpen={onOpenEvidence} />
      </Shell>
    );

  if (t === "no_evidence")
    return <Shell byline="orchestrator"><div className="flex items-center gap-2 text-sm text-[#E8B931]"><AlertTriangle size={15} />{card.message}</div></Shell>;

  if (t === "degraded")
    return <Shell byline="orchestrator" tag="degraded"><div className="flex items-center gap-2 text-sm text-[#8B98A5]"><CheckCircle2 size={15} />{card.message}</div><EvidenceTrail refs={card.citation_refs} onOpen={onOpenEvidence} /></Shell>;

  return <Shell byline="orchestrator"><pre className="text-xs text-[#8B98A5] whitespace-pre-wrap">{JSON.stringify(card, null, 2)}</pre></Shell>;
}
