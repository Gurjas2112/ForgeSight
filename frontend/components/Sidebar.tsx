"use client";
import { useEffect, useRef, useState } from "react";
import { Send, X, Bot, ChevronRight, ThumbsUp, ThumbsDown, Check } from "lucide-react";
import { postApprove, postChat, postFeedback } from "@/lib/api";
import type { Card, Delegation } from "@/lib/types";
import { CardView } from "./Cards";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Turn = { role: "user" } | { role: "assistant"; card: Card; delegations: Delegation[]; pending?: Record<string, unknown> | null };
type Msg = ({ role: "user"; text: string }) | (Turn & { role: "assistant"; card: Card; delegations: Delegation[]; pending?: Record<string, unknown> | null });

export function Sidebar({ equipmentId, greeting }: { equipmentId: string; greeting?: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState<string>();
  const [drawer, setDrawer] = useState<{ ref: string; content: string; source?: string } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  async function openEvidence(ref: string) {
    setDrawer({ ref, content: "Loading…" });
    try {
      const r = await fetch(`${API}/evidence?ref=${encodeURIComponent(ref)}`).then((x) => x.json());
      setDrawer({ ref, content: r.content, source: r.source });
    } catch { setDrawer({ ref, content: "Could not load evidence." }); }
  }

  async function ask(text: string) {
    if (!text.trim() || busy) return;
    setMsgs((m) => [...m, { role: "user", text }]);
    setInput(""); setBusy(true);
    try {
      const r = await postChat({ message: text, equipment_id: equipmentId, session_id: session });
      setSession(r.session_id);
      if (r.card) setMsgs((m) => [...m, { role: "assistant", card: r.card!, delegations: r.delegations, pending: r.awaiting_approval ? r.pending_action : null }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", card: { card_type: "degraded", message: `Backend unreachable: ${e}` }, delegations: [] }]);
    } finally { setBusy(false); }
  }

  async function decide(approved: boolean) {
    if (!session) return;
    setBusy(true);
    try {
      const r = await postApprove(session, approved);
      if (r.card) setMsgs((m) => [...m, { role: "assistant", card: r.card!, delegations: r.delegations }]);
    } finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col h-full panel overflow-hidden">
      <div className="flex items-center gap-2 px-4 h-12 border-b border-[#232B35]">
        <Bot size={16} className="text-[#4A90D9]" />
        <span className="font-medium text-sm">Copilot</span>
        <span className="text-xs text-[#8B98A5] ml-auto mono">{equipmentId}</span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {greeting && msgs.length === 0 && (
          <div className="text-sm text-[#9fb0c0] panel p-3 bg-[#1C232C]">{greeting}</div>
        )}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="text-sm bg-[#1C232C] rounded-lg px-3 py-2 ml-8 text-[#E6EDF3]">{m.text}</div>
          ) : (
            <div key={i} className="space-y-2">
              {m.delegations?.length > 0 && (
                <div className="text-xs text-[#8B98A5] space-y-0.5 pl-1">
                  {m.delegations.map((d, j) => (
                    <div key={j} className="flex items-center gap-1"><ChevronRight size={11} className="text-[#4A90D9]" />
                      <span className="capitalize">{d.agent.replace(/_/g, " ")}</span>: {d.text}</div>
                  ))}
                </div>
              )}
              <CardView card={m.card} onOpenEvidence={openEvidence} />
              <FeedbackBar equipmentId={equipmentId}
                faultCode={(m.card as { fault?: string }).fault}
                cardType={(m.card as { card_type?: string }).card_type} />
              {m.pending && (
                <div className="panel p-3 bg-[#E8B93114] border-[#E8B93155] slidein">
                  <div className="text-sm font-medium text-[#E8B931] mb-1">Approval required</div>
                  <div className="text-xs text-[#c3ced9] mb-2 mono">{JSON.stringify(m.pending)}</div>
                  <div className="flex gap-2">
                    <button onClick={() => decide(true)} className="px-3 py-1 rounded bg-[#3FB68B] text-black text-sm font-medium">Approve</button>
                    <button onClick={() => decide(false)} className="px-3 py-1 rounded bg-[#E5484D] text-white text-sm font-medium">Reject</button>
                  </div>
                  <div className="text-[10px] text-[#8B98A5] mt-2">Agents propose; humans commit; everything is audited.</div>
                </div>
              )}
            </div>
          )
        )}
        {busy && (
          <div className="flex items-center gap-2 text-xs text-[#8B98A5] pl-1 slidein">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#4A90D9] animate-pulse" />
            Running governed pipeline…
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="p-3 border-t border-[#232B35] flex flex-wrap gap-1.5">
        {["diagnose the F3 trip", "can it wait till Sunday?", "what should we tackle first?", "which equipment had the most downtime?"].map((q) => (
          <button key={q} onClick={() => ask(q)} disabled={busy}
            className="text-[11px] px-2 py-1 rounded bg-[#1C232C] border border-[#232B35] text-[#9fb0c0] hover:border-[#4A90D9] disabled:opacity-40">{q}</button>
        ))}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); ask(input); }} className="p-3 pt-0 flex gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask the maintenance copilot…"
          className="flex-1 bg-[#0E1116] border border-[#232B35] rounded-lg px-3 py-2 text-sm outline-none focus:border-[#4A90D9]" />
        <button disabled={busy} className="px-3 rounded-lg bg-[#4A90D9] text-white disabled:opacity-40"><Send size={16} /></button>
      </form>

      {drawer && (
        <div className="absolute inset-0 bg-black/50 flex justify-end z-30" onClick={() => setDrawer(null)}>
          <div className="w-[420px] max-w-[90%] h-full bg-[#161B22] border-l border-[#232B35] p-4 overflow-y-auto slidein" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <span className="mono text-sm text-[#4A90D9]">{drawer.ref}</span>
              <button onClick={() => setDrawer(null)}><X size={18} className="text-[#8B98A5]" /></button>
            </div>
            <div className="text-xs text-[#8B98A5] mb-2">{drawer.source}</div>
            <pre className="text-sm text-[#c3ced9] whitespace-pre-wrap leading-relaxed">{drawer.content}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

/** FR-6 — feedback capture. 'Fixed it' flips the matching breakdown record to engineer-verified. */
function FeedbackBar({ equipmentId, faultCode, cardType }:
  { equipmentId: string; faultCode?: string; cardType?: string }) {
  const [sent, setSent] = useState<string>();
  if (cardType === "degraded" || cardType === "no_evidence") return null;
  async function send(verdict: "up" | "down" | "fixed") {
    try {
      const r = await postFeedback({ verdict, equipment_id: equipmentId, fault_code: faultCode });
      setSent(verdict === "fixed"
        ? `✓ Saved to ${equipmentId} logbook${r.verified_record ? ` · ${r.verified_record} verified` : ""}`
        : "Thanks — feedback recorded");
    } catch { setSent("Could not save feedback"); }
  }
  if (sent) return <div className="text-[10px] text-[#3FB68B] pl-1">{sent}</div>;
  return (
    <div className="flex items-center gap-2 pl-1 text-[#8B98A5]">
      <span className="text-[10px]">Helpful?</span>
      <button type="button" title="Helpful" onClick={() => send("up")} className="hover:text-[#3FB68B]"><ThumbsUp size={13} /></button>
      <button type="button" title="Not helpful" onClick={() => send("down")} className="hover:text-[#E5484D]"><ThumbsDown size={13} /></button>
      <button type="button" onClick={() => send("fixed")}
        className="text-[10px] inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#1C232C] border border-[#232B35] hover:border-[#3FB68B] hover:text-[#3FB68B]">
        <Check size={11} /> This fixed it</button>
    </div>
  );
}
