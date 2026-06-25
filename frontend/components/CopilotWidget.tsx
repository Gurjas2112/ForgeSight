"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Send, X, Bot, ChevronRight, History, Plus, MessageSquare } from "lucide-react";
import { postApprove, postChat, getChatSessions, getChatMessages } from "@/lib/api";
import { authConfigured } from "@/lib/supabase";
import { useAuth } from "./AuthProvider";
import type { Card, Delegation, ChatSessionSummary } from "@/lib/types";
import { CardView } from "./Cards";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Msg =
  | { role: "user"; text: string; ts?: string }
  | { role: "assistant"; card: Card; delegations: Delegation[]; pending?: Record<string, unknown> | null; ts?: string };

function fmtTime(ts?: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  return isNaN(d.getTime()) ? "" : d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Global, fixed-position copilot. Launcher (bottom-right) opens a fixed-height panel whose
 *  message list scrolls internally — the page never grows as the conversation continues.
 *  Restores per-user conversation history (with timestamps) from the backend. */
export function CopilotWidget() {
  const { session, email, loading } = useAuth();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string>();
  const [drawer, setDrawer] = useState<{ ref: string; content: string; source?: string } | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  // remember the active conversation per user across reloads
  const storeKey = email ? `forgesight.copilot.session.${email}` : "forgesight.copilot.session";

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy, open]);

  const restore = useCallback(async (id: string) => {
    setBusy(true);
    try {
      const history = await getChatMessages(id);
      const restored: Msg[] = history
        .filter((h) => h.role === "user" || h.role === "assistant")
        .map((h) => h.role === "user"
          ? { role: "user", text: h.content || "", ts: h.created_at }
          : { role: "assistant", card: (h.card || { card_type: "degraded", message: h.content || "" }) as Card, delegations: [], ts: h.created_at });
      setMsgs(restored);
      setSessionId(id);
    } catch { /* a stale/foreign session id just starts fresh */ }
    finally { setBusy(false); }
  }, []);

  // on first open, load the session list and resume the last conversation
  useEffect(() => {
    if (!open) return;
    getChatSessions().then(setSessions).catch(() => {});
    if (!sessionId) {
      const saved = typeof window !== "undefined" ? localStorage.getItem(storeKey) : null;
      if (saved) restore(saved);
    }
  }, [open, sessionId, storeKey, restore]);

  async function openEvidence(ref: string) {
    setDrawer({ ref, content: "Loading…" });
    try {
      const r = await fetch(`${API}/evidence?ref=${encodeURIComponent(ref)}`).then((x) => x.json());
      setDrawer({ ref, content: r.content, source: r.source });
    } catch { setDrawer({ ref, content: "Could not load evidence." }); }
  }

  async function ask(text: string) {
    if (!text.trim() || busy) return;
    setMsgs((m) => [...m, { role: "user", text, ts: new Date().toISOString() }]);
    setInput(""); setBusy(true);
    try {
      const r = await postChat({ message: text, session_id: sessionId });
      setSessionId(r.session_id);
      if (typeof window !== "undefined") localStorage.setItem(storeKey, r.session_id);
      if (r.card) setMsgs((m) => [...m, { role: "assistant", card: r.card!, delegations: r.delegations, pending: r.awaiting_approval ? r.pending_action : null, ts: new Date().toISOString() }]);
      getChatSessions().then(setSessions).catch(() => {});
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", card: { card_type: "degraded", message: `Backend unreachable: ${e}` }, delegations: [], ts: new Date().toISOString() }]);
    } finally { setBusy(false); }
  }

  async function decide(approved: boolean) {
    if (!sessionId) return;
    setBusy(true);
    try {
      const r = await postApprove(sessionId, approved);
      if (r.card) setMsgs((m) => [...m, { role: "assistant", card: r.card!, delegations: r.delegations, ts: new Date().toISOString() }]);
    } finally { setBusy(false); }
  }

  function newChat() {
    setMsgs([]); setSessionId(undefined); setShowHistory(false);
    if (typeof window !== "undefined") localStorage.removeItem(storeKey);
  }

  // render only for authenticated users (or local demo where auth isn't configured)
  if (loading) return null;
  if (authConfigured() && !session) return null;

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} aria-label="Open maintenance copilot"
        className="fixed bottom-5 right-5 z-40 w-14 h-14 rounded-full bg-[#4A90D9] text-white shadow-lg flex items-center justify-center hover:bg-[#3f7fc2] transition-colors">
        <Bot size={24} />
      </button>
    );
  }

  return (
    <div className="fixed bottom-5 right-5 z-40 w-[380px] max-w-[calc(100vw-2.5rem)] h-[600px] max-h-[80vh] flex flex-col panel overflow-hidden shadow-2xl border border-[#232B35] rounded-xl">
      <div className="flex items-center gap-2 px-3 h-12 border-b border-[#232B35] shrink-0">
        <Bot size={16} className="text-[#4A90D9]" />
        <span className="font-medium text-sm">Maintenance Copilot</span>
        <div className="ml-auto flex items-center gap-1">
          <button onClick={() => setShowHistory((v) => !v)} title="Conversation history" className="p-1.5 rounded hover:bg-[#1C232C] text-[#8B98A5]"><History size={15} /></button>
          <button onClick={newChat} title="New conversation" className="p-1.5 rounded hover:bg-[#1C232C] text-[#8B98A5]"><Plus size={15} /></button>
          <button onClick={() => setOpen(false)} title="Minimise" className="p-1.5 rounded hover:bg-[#1C232C] text-[#8B98A5]"><X size={16} /></button>
        </div>
      </div>

      {showHistory && (
        <div className="border-b border-[#232B35] max-h-[200px] overflow-y-auto bg-[#0E1116] shrink-0">
          {sessions.length === 0 && <div className="text-xs text-[#8B98A5] p-3">No past conversations yet.</div>}
          {sessions.map((s) => (
            <button key={s.id} onClick={() => { restore(s.id); setShowHistory(false); }}
              className={`w-full text-left px-3 py-2 hover:bg-[#1C232C] flex items-start gap-2 ${s.id === sessionId ? "bg-[#1C232C]" : ""}`}>
              <MessageSquare size={13} className="text-[#4A90D9] mt-0.5 shrink-0" />
              <div className="min-w-0">
                <div className="text-xs text-[#E6EDF3] truncate">{s.title || "Conversation"}</div>
                <div className="text-[10px] text-[#8B98A5]">{fmtTime(s.updated_at)} · {s.message_count} msgs{s.equipment_id ? ` · ${s.equipment_id}` : ""}</div>
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {msgs.length === 0 && (
          <div className="text-sm text-[#9fb0c0] panel p-3 bg-[#1C232C]">
            Ask about any equipment — diagnosis, root cause, can-it-wait, priority, spares, or downtime analytics. Every answer is cited and audited.
          </div>
        )}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="ml-8">
              <div className="text-sm bg-[#1C232C] rounded-lg px-3 py-2 text-[#E6EDF3]">{m.text}</div>
              {m.ts && <div className="text-[10px] text-[#5b6672] mt-0.5 text-right mono">{fmtTime(m.ts)}</div>}
            </div>
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
              {m.ts && <div className="text-[10px] text-[#5b6672] pl-1 mono">{fmtTime(m.ts)}</div>}
              {m.pending && (
                <div className="panel p-3 bg-[#E8B93114] border-[#E8B93155] slidein">
                  <div className="text-sm font-medium text-[#E8B931] mb-1">Approval required</div>
                  <div className="text-xs text-[#c3ced9] mb-2 mono break-all">{JSON.stringify(m.pending)}</div>
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

      <div className="p-2 border-t border-[#232B35] flex flex-wrap gap-1.5 shrink-0">
        {["diagnose the F3 trip", "can it wait till Sunday?", "what should we tackle first?", "which equipment had the most downtime?"].map((q) => (
          <button key={q} onClick={() => ask(q)} disabled={busy}
            className="text-[11px] px-2 py-1 rounded bg-[#1C232C] border border-[#232B35] text-[#9fb0c0] hover:border-[#4A90D9] disabled:opacity-40">{q}</button>
        ))}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); ask(input); }} className="p-2 pt-0 flex gap-2 shrink-0">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask the maintenance copilot…"
          className="flex-1 bg-[#0E1116] border border-[#232B35] rounded-lg px-3 py-2 text-sm outline-none focus:border-[#4A90D9]" />
        <button type="submit" disabled={busy} aria-label="Send message" className="px-3 rounded-lg bg-[#4A90D9] text-white disabled:opacity-40"><Send size={16} /></button>
      </form>

      {drawer && (
        <div className="absolute inset-0 bg-black/50 flex justify-end z-30" onClick={() => setDrawer(null)}>
          <div className="w-[320px] max-w-[90%] h-full bg-[#161B22] border-l border-[#232B35] p-4 overflow-y-auto slidein" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <span className="mono text-sm text-[#4A90D9]">{drawer.ref}</span>
              <button type="button" aria-label="Close evidence" onClick={() => setDrawer(null)}><X size={18} className="text-[#8B98A5]" /></button>
            </div>
            <div className="text-xs text-[#8B98A5] mb-2">{drawer.source}</div>
            <pre className="text-sm text-[#c3ced9] whitespace-pre-wrap leading-relaxed">{drawer.content}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
