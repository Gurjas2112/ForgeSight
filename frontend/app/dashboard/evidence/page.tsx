"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { searchEvidence } from "@/lib/api";
import type { SearchItem } from "@/lib/types";
import { EvidenceChip } from "@/components/ui";
import { AuthGuard } from "@/components/AuthGuard";

const TYPE_FILTERS = ["manual", "sop", "report", "incident", "spare", "work_order", "sensor"];

function EvidenceSearch() {
  const [q, setQ] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [items, setItems] = useState<SearchItem[]>([]);
  const [busy, setBusy] = useState(false);

  async function run(query = q) {
    setBusy(true);
    try {
      const r = await searchEvidence({ q: query, types: types.join(",") || undefined });
      setItems(r.items);
    } catch { setItems([]); }
    finally { setBusy(false); }
  }

  useEffect(() => { run(""); }, []);

  function toggleType(t: string) {
    setTypes((prev) => prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]);
  }

  return (
    <>
      <h1 className="text-xl font-semibold mb-1">Evidence search</h1>
      <p className="text-sm text-[#8B98A5] mb-4">Manuals, SOPs, incidents, sensor events, work orders, and spares — searchable evidence for the AI workflow.</p>
      <form onSubmit={(e) => { e.preventDefault(); run(); }} className="flex gap-2 mb-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search corpus…"
          className="flex-1 bg-[#0E1116] border border-[#232B35] rounded-lg px-3 py-2 text-sm outline-none focus:border-[#4A90D9]" />
        <button type="submit" disabled={busy} className="px-4 rounded-lg bg-[#4A90D9] text-white text-sm flex items-center gap-1">
          <Search size={14} /> Search
        </button>
      </form>
      <div className="flex flex-wrap gap-1.5 mb-4">
        {TYPE_FILTERS.map((t) => (
          <button key={t} type="button" onClick={() => toggleType(t)}
            className={`text-[11px] px-2 py-1 rounded border ${types.includes(t) ? "border-[#4A90D9] text-[#4A90D9]" : "border-[#232B35] text-[#8B98A5]"}`}>
            {t.replace("_", " ")}
          </button>
        ))}
      </div>
      <div className="space-y-2">
        {items.map((it) => (
          <div key={`${it.type}-${it.ref}`} className="panel p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <EvidenceChip kind={it.type === "spare" ? "spares_record" : it.type} label={it.ref} />
                <div className="font-medium text-sm mt-1">{it.title}</div>
                <div className="text-xs text-[#8B98A5] mt-0.5">{it.excerpt}</div>
              </div>
              {it.equipment_id && (
                <Link href={`/equipment/${it.equipment_id}?prompt=${encodeURIComponent(`Tell me about ${it.ref}`)}`}
                  className="text-xs text-[#4A90D9] whitespace-nowrap hover:underline">Ask copilot</Link>
              )}
            </div>
          </div>
        ))}
        {!busy && items.length === 0 && <div className="text-sm text-[#8B98A5] panel p-4">No results.</div>}
      </div>
    </>
  );
}

export default function Page() {
  return <AuthGuard><EvidenceSearch /></AuthGuard>;
}
