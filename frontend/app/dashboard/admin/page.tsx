"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, Users, MessagesSquare, Database, ClipboardList, ScrollText, Cpu, Coins } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { AuthGuard } from "@/components/AuthGuard";
import { ModelScorecard } from "@/components/ModelScorecard";
import { useAuth } from "@/components/AuthProvider";
import { getAdminMetrics, getAdminUsers, getAdminAudit, getAdminLlmUsage } from "@/lib/api";
import type { AdminMetrics, AdminUser, AuditEvent, LlmUsageDetail } from "@/lib/types";

function fmtNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export default function AdminPage() {
  return (
    <AuthGuard>
      <AdminBody />
    </AuthGuard>
  );
}

function AdminBody() {
  const { role, loading } = useAuth();
  const router = useRouter();
  const [m, setM] = useState<AdminMetrics>();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [llm, setLlm] = useState<LlmUsageDetail>();
  const [err, setErr] = useState<string>();

  // engineers may not view system metrics — bounce them to the shared overview.
  useEffect(() => { if (!loading && role && role !== "admin") router.replace("/dashboard"); }, [loading, role, router]);

  useEffect(() => {
    if (role !== "admin") return;
    getAdminMetrics().then(setM).catch((e) => setErr(String(e)));
    getAdminUsers().then(setUsers).catch(() => {});
    getAdminAudit(50).then(setAudit).catch(() => {});
    getAdminLlmUsage(14).then(setLlm).catch(() => {});
  }, [role]);

  if (role && role !== "admin") return null;

  return (
    <div>
      <h1 className="text-xl font-semibold flex items-center gap-2 mb-1">
        <ShieldCheck size={18} className="text-[#4A90D9]" /> Admin · System Metrics
      </h1>
      <p className="text-sm text-[#8B98A5] mb-5">Live aggregates across accounts, knowledge base, conversations, feedback, work orders and governance — every value is queried from the operational database.</p>
      {err && <div className="panel p-3 mb-4 text-sm text-[#E5484D]">Could not load admin metrics: {err}</div>}

      {m && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            <Stat icon={<Users size={15} />} label="Accounts" value={m.accounts.total}
              sub={Object.entries(m.accounts.by_role).map(([r, n]) => `${n} ${r}`).join(" · ") || "—"} />
            <Stat icon={<MessagesSquare size={15} />} label="Chat sessions" value={m.conversations.sessions}
              sub={`${m.conversations.messages} messages · ${m.conversations.active_24h} active 24h`} />
            <Stat icon={<Database size={15} />} label="Knowledge chunks" value={m.knowledge.doc_chunks}
              sub={`${m.knowledge.equipment} equipment · ${m.knowledge.breakdown_records} breakdowns`} />
            <Stat icon={<ClipboardList size={15} />} label="Work orders" value={m.work_orders.total}
              sub={Object.entries(m.work_orders.by_status).map(([s, n]) => `${n} ${s}`).join(" · ") || "none yet"} />
            <Stat icon={<ScrollText size={15} />} label="Audit events" value={m.governance.audit_events_total}
              sub={`${m.governance.audit_events_24h} in 24h · ${m.governance.denied_24h} denied`} />
            <Stat label="Open alerts" value={m.alerts.open}
              sub={`${m.plant.at_risk_count} assets at risk`} />
            <Stat label="Plant availability" value={`${m.plant.availability_pct}%`}
              sub={m.plant.downtime_at_risk_label} />
            <Stat label="Feedback" value={m.feedback.total}
              sub={Object.entries(m.feedback.by_verdict).map(([v, n]) => `${n} ${v}`).join(" · ") || "none yet"} />
          </div>

          {/* LLM token-usage monitor */}
          <div className="mt-6">
            <h2 className="text-sm font-medium mb-2 text-[#8B98A5] flex items-center gap-2">
              <Cpu size={15} className="text-[#4A90D9]" /> LLM token usage & caching —
              <span className="mono text-[#9fb0c0]">{m.llm.backend}:{m.llm.model}</span>
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              <Stat icon={<Coins size={15} />} label="Total tokens" value={fmtNum(m.llm.total_tokens)}
                sub={`${fmtNum(m.llm.prompt_tokens)} in · ${fmtNum(m.llm.completion_tokens)} out`} />
              <Stat label="Tokens (24h)" value={fmtNum(m.llm.tokens_24h)} sub={`${m.llm.calls} total calls`} />
              <Stat label="Cache hit rate" value={`${Math.round(m.llm.cache_hit_rate * 100)}%`}
                sub={`${m.llm.cached_calls} hits · ${m.llm.cache_entries} cached`} />
              <Stat label="Est. cost" value={`$${m.llm.est_cost_usd.toFixed(2)}`} sub="Groq list price" />
              <Stat label="Cached calls" value={m.llm.cached_calls} sub="0 tokens spent" />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-3">
              <div className="panel p-4 lg:col-span-2">
                <div className="text-xs text-[#8B98A5] mb-2">Daily tokens (last 14 days)</div>
                <div className="w-full h-40">
                  <ResponsiveContainer>
                    <BarChart data={llm?.series ?? []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#232B35" />
                      <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#8B98A5" }} tickFormatter={(d: string) => d.slice(5)} />
                      <YAxis tick={{ fontSize: 10, fill: "#8B98A5" }} tickFormatter={(v: number) => fmtNum(v)} width={38} />
                      <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #232B35", fontSize: 12 }} />
                      <Bar dataKey="tokens" fill="#4A90D9" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div className="panel p-4">
                <div className="text-xs text-[#8B98A5] mb-2">By call type</div>
                <table className="w-full text-xs">
                  <thead><tr className="text-[#8B98A5] text-left">
                    <th className="py-1">Type</th><th className="py-1 text-right">Calls</th><th className="py-1 text-right">Tokens</th>
                  </tr></thead>
                  <tbody>
                    {(llm?.by_type ?? []).map((t) => (
                      <tr key={t.call_type} className="border-t border-[#232B35]">
                        <td className="py-1.5">{t.call_type}</td>
                        <td className="py-1.5 text-right">{t.calls} <span className="text-[#5b6672]">({t.cached}c)</span></td>
                        <td className="py-1.5 text-right mono">{fmtNum(t.tokens)}</td>
                      </tr>
                    ))}
                    {(!llm || llm.by_type.length === 0) && <tr><td colSpan={3} className="py-2 text-[#8B98A5]">No LLM calls recorded yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="text-[11px] text-[#8B98A5] mt-2">
              Every synthesis/classify call is metered; identical query+evidence is served from the
              <span className="text-[#9fb0c0]"> llm_cache</span> (0 tokens). Cost is an estimate at Groq list price
              ($0.59/1M in · $0.79/1M out).
            </p>
          </div>

          <ModelScorecard />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
            <div className="panel p-4">
              <h2 className="text-sm font-medium mb-3 flex items-center gap-2"><Users size={15} className="text-[#4A90D9]" /> Accounts ({users.length})</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="text-[#8B98A5] text-left">
                    <th className="py-1 pr-3">Name</th><th className="py-1 pr-3">Role</th><th className="py-1">Area</th>
                  </tr></thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className="border-t border-[#232B35]">
                        <td className="py-1.5 pr-3">{u.full_name || "—"}</td>
                        <td className="py-1.5 pr-3"><span className={u.role === "admin" ? "text-[#4A90D9]" : "text-[#9fb0c0]"}>{u.role}</span></td>
                        <td className="py-1.5">{u.area || "—"}</td>
                      </tr>
                    ))}
                    {users.length === 0 && <tr><td colSpan={3} className="py-2 text-[#8B98A5]">No profiles found.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="panel p-4">
              <h2 className="text-sm font-medium mb-3 flex items-center gap-2"><ScrollText size={15} className="text-[#4A90D9]" /> Recent governance audit</h2>
              <div className="space-y-1.5 max-h-[320px] overflow-y-auto">
                {audit.map((a, i) => (
                  <div key={i} className="text-xs flex items-start gap-2">
                    <span className={`mt-0.5 inline-block w-1.5 h-1.5 rounded-full ${a.allowed ? "bg-[#3FB68B]" : "bg-[#E5484D]"}`} />
                    <div>
                      <span className="text-[#c3ced9]">{a.agent_name || "system"}</span>
                      <span className="text-[#8B98A5]"> · {a.action || "—"}{a.resource ? ` (${a.resource})` : ""}</span>
                      {a.reason && <div className="text-[#8B98A5]">{a.reason}</div>}
                      <div className="text-[10px] text-[#5b6672] mono">{a.ts}</div>
                    </div>
                  </div>
                ))}
                {audit.length === 0 && <div className="text-xs text-[#8B98A5]">No audit events yet.</div>}
              </div>
            </div>
          </div>
        </>
      )}
      {!m && !err && <div className="text-sm text-[#8B98A5]">Loading system metrics…</div>}
    </div>
  );
}

function Stat({ icon, label, value, sub }: { icon?: React.ReactNode; label: string; value: string | number; sub?: string }) {
  return (
    <div className="panel p-4">
      <div className="text-xs text-[#8B98A5] flex items-center gap-1.5">{icon}{label}</div>
      <div className="text-2xl font-semibold mt-1 text-[#E6EDF3]">{value}</div>
      {sub && <div className="text-[11px] text-[#8B98A5] mt-1">{sub}</div>}
    </div>
  );
}
