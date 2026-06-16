"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Html, Grid, ContactShadows } from "@react-three/drei";
import type { Mesh } from "three";
import { getAlerts, getEquipment, getWorkOrders, reportUrl } from "@/lib/api";
import type { Alert, Equipment, WorkOrder } from "@/lib/types";

type Sev = "critical" | "high" | "warning" | "ok";
const SEV_COLOR: Record<Sev, string> = {
  critical: "#E5484D", high: "#FF6A2B", warning: "#E8B931", ok: "#3FB68B",
};
const SEV_LABEL: Record<Sev, string> = {
  critical: "CRITICAL", high: "EARLY WARNING", warning: "ABNORMAL", ok: "HEALTHY",
};

function sevOf(eq: Equipment, al: Alert[]): Sev {
  if (al.some((a) => a.severity === "critical")) return "critical";
  if (eq.id === "hsm-f3-stand") return "critical";            // F3 tripped (matches dashboard)
  if (al.some((a) => a.severity === "high")) return "high";
  if (eq.is_anomalous && (eq.rul_days ?? 99) < 7) return "high";
  if (eq.is_anomalous) return "warning";
  return "ok";
}
function maintStatus(sev: Sev): string {
  return sev === "critical" ? "Action required"
    : sev === "high" ? "Maintenance due"
    : sev === "warning" ? "Under watch" : "Operational";
}

type Placed = {
  eq: Equipment; sev: Sev; pos: [number, number, number];
  shape: "fan" | "caster" | "furnace" | "crane" | "mill"; height: number;
};

function shapeOf(name: string): Placed["shape"] {
  const n = name.toLowerCase();
  if (n.includes("fan")) return "fan";
  if (n.includes("caster")) return "caster";
  if (n.includes("furnace") || n.includes("stove") || n.includes("blast")) return "furnace";
  if (n.includes("crane") || n.includes("ladle")) return "crane";
  return "mill";
}

/** Deterministic plant floor-plan: group by zone, lay zones on a grid, assets in a row per zone. */
function layout(eq: Equipment[], alertsByEq: Record<string, Alert[]>) {
  const zones = new Map<string, Equipment[]>();
  for (const e of eq) zones.set(e.zone, [...(zones.get(e.zone) || []), e]);
  const zoneList = [...zones.entries()];
  const cols = Math.max(1, Math.ceil(Math.sqrt(zoneList.length)));
  const rows = Math.ceil(zoneList.length / cols);
  const CELL = 7;
  const offX = ((cols - 1) * CELL) / 2;
  const offZ = ((rows - 1) * CELL) / 2;

  const placed: Placed[] = [];
  const zoneMarkers: { name: string; pos: [number, number, number] }[] = [];
  zoneList.forEach(([zone, items], zi) => {
    const zc = zi % cols, zr = Math.floor(zi / cols);
    const cx = zc * CELL - offX, cz = zr * CELL - offZ;
    zoneMarkers.push({ name: zone, pos: [cx, 0, cz - CELL / 2 + 0.6] });
    items.forEach((e, i) => {
      const x = cx + (i - (items.length - 1) / 2) * 2.3;
      const shape = shapeOf(e.name);
      const height = shape === "furnace" ? 2.6 : shape === "fan" ? 1.6 : shape === "caster" ? 1.0 : 1.3;
      placed.push({ eq: e, sev: sevOf(e, alertsByEq[e.id] || []), pos: [x, 0, cz], shape, height });
    });
  });
  return { placed, zoneMarkers, extent: Math.max(cols, rows) * CELL };
}

function AssetGeometry({ shape, h }: { shape: Placed["shape"]; h: number }) {
  switch (shape) {
    case "fan":     return <cylinderGeometry args={[0.7, 0.7, h, 24]} />;
    case "caster":  return <boxGeometry args={[2.0, h, 0.9]} />;
    case "furnace": return <cylinderGeometry args={[0.9, 1.1, h, 8]} />;
    case "crane":   return <boxGeometry args={[0.7, h, 0.7]} />;
    default:        return <boxGeometry args={[1.3, h, 1.3]} />;
  }
}

function Asset({ p, selected, onSelect }: { p: Placed; selected: boolean; onSelect: () => void }) {
  const ref = useRef<Mesh>(null);
  const [hovered, setHovered] = useState(false);
  const base = p.sev === "critical" ? 0.55 : p.sev === "high" ? 0.4 : 0.2;
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const mat = ref.current.material as unknown as { emissiveIntensity: number };
    const pulse = p.sev === "critical" ? 0.35 * (0.5 + 0.5 * Math.sin(clock.elapsedTime * 4)) : 0;
    mat.emissiveIntensity = base + pulse + (hovered ? 0.25 : 0);
  });
  const color = SEV_COLOR[p.sev];
  return (
    <group position={p.pos}>
      {/* base pad */}
      <mesh position={[0, 0.05, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[1.25, 32]} />
        <meshStandardMaterial color="#161B22" />
      </mesh>
      {/* selection ring */}
      {selected && (
        <mesh position={[0, 0.07, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[1.3, 1.5, 40]} />
          <meshBasicMaterial color="#4A90D9" />
        </mesh>
      )}
      {/* the asset */}
      <mesh
        ref={ref}
        position={[0, p.height / 2 + 0.1, 0]}
        onClick={(e) => { e.stopPropagation(); onSelect(); }}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { setHovered(false); document.body.style.cursor = "auto"; }}
      >
        <AssetGeometry shape={p.shape} h={p.height} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={base} metalness={0.3} roughness={0.5} />
      </mesh>
      {/* crane jib */}
      {p.shape === "crane" && (
        <mesh position={[0.9, p.height + 0.1, 0]}>
          <boxGeometry args={[2.4, 0.18, 0.18]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={base} />
        </mesh>
      )}
      {/* label */}
      <Html position={[0, p.height + 0.7, 0]} center distanceFactor={14} occlude={false}>
        <div style={{
          whiteSpace: "nowrap", fontSize: 11, padding: "2px 7px", borderRadius: 6,
          background: "rgba(13,17,22,0.85)", border: `1px solid ${color}`, color: "#E6EDF3",
          fontFamily: "ui-monospace, monospace", pointerEvents: "none", transform: "translateY(-2px)",
        }}>
          {p.eq.name}{p.eq.rul_days != null ? ` · RUL ${p.eq.rul_days}d` : ""}
        </div>
      </Html>
    </group>
  );
}

function Scene({ placed, zoneMarkers, extent, selectedId, onSelect }: {
  placed: Placed[]; zoneMarkers: { name: string; pos: [number, number, number] }[];
  extent: number; selectedId: string | null; onSelect: (id: string | null) => void;
}) {
  return (
    <>
      <hemisphereLight args={["#9fb6d6", "#0b0e13", 0.9]} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[10, 16, 8]} intensity={1.1} />
      <Grid args={[extent + 6, extent + 6]} cellSize={1} cellColor="#1b2430" sectionSize={7}
        sectionColor="#26405c" infiniteGrid={false} fadeDistance={60} position={[0, 0.01, 0]} />
      <ContactShadows position={[0, 0.02, 0]} opacity={0.4} scale={extent + 10} blur={2.4} far={12} />
      {zoneMarkers.map((z) => (
        <Html key={z.name} position={z.pos} center distanceFactor={20}>
          <div style={{
            whiteSpace: "nowrap", fontSize: 12, letterSpacing: 1, textTransform: "uppercase",
            color: "#8B98A5", fontWeight: 600, pointerEvents: "none",
          }}>{z.name}</div>
        </Html>
      ))}
      {placed.map((p) => (
        <Asset key={p.eq.id} p={p} selected={selectedId === p.eq.id} onSelect={() => onSelect(p.eq.id)} />
      ))}
      <OrbitControls makeDefault enablePan maxPolarAngle={Math.PI / 2.15} minDistance={6} maxDistance={40} />
    </>
  );
}

export default function PlantTwin3D() {
  const [eq, setEq] = useState<Equipment[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [err, setErr] = useState<string>();

  useEffect(() => {
    getEquipment().then(setEq).catch((e) => setErr(String(e)));
    getAlerts().then(setAlerts).catch(() => {});
    getWorkOrders().then(setWorkOrders).catch(() => {});
    const a = new URLSearchParams(window.location.search).get("asset");
    if (a) setSel(a);
  }, []);

  const alertsByEq = useMemo(() => {
    const m: Record<string, Alert[]> = {};
    for (const a of alerts) (m[a.equipment_id] ||= []).push(a);
    return m;
  }, [alerts]);

  const woByEq = useMemo(() => {
    const m: Record<string, WorkOrder[]> = {};
    for (const w of workOrders) if (w.status !== "completed" && w.status !== "cancelled") {
      (m[w.equipment_id] ||= []).push(w);
    }
    return m;
  }, [workOrders]);

  const { placed, zoneMarkers, extent } = useMemo(
    () => layout(eq, alertsByEq), [eq, alertsByEq]);

  const selected = placed.find((p) => p.eq.id === sel) || null;
  const selectedWOs = selected ? (woByEq[selected.eq.id] || []) : [];

  return (
    <div className="relative h-[calc(100vh-3.5rem)] w-full">
      {/* legend */}
      <div className="absolute top-3 left-3 z-10 panel p-3 text-xs space-y-1.5">
        <div className="font-medium text-[#E6EDF3] mb-1">Plant health</div>
        {(["critical", "high", "warning", "ok"] as Sev[]).map((s) => (
          <div key={s} className="flex items-center gap-2 text-[#9fb0c0]">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: SEV_COLOR[s] }} />
            {SEV_LABEL[s]}
          </div>
        ))}
        <div className="text-[10px] text-[#8B98A5] pt-1">drag to orbit · scroll to zoom · click an asset</div>
      </div>

      {err && <div className="absolute top-3 right-3 z-10 panel p-3 text-sm text-[#E5484D]">Backend unreachable ({err}).</div>}

      <Canvas camera={{ position: [13, 11, 13], fov: 45 }} onPointerMissed={() => setSel(null)}
        gl={{ antialias: true }} dpr={[1, 2]} style={{ background: "#0B0E13" }}>
        <Scene placed={placed} zoneMarkers={zoneMarkers} extent={extent} selectedId={sel} onSelect={setSel} />
      </Canvas>

      {/* inspector */}
      {selected && (
        <div className="absolute top-0 right-0 h-full w-[360px] max-w-[88%] bg-[#0E1116]/95 border-l border-[#232B35] p-4 overflow-y-auto z-10 slidein">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-lg font-semibold">{selected.eq.name}</div>
              <div className="text-xs text-[#8B98A5] mono">{selected.eq.id} · {selected.eq.zone} · criticality {selected.eq.criticality}</div>
            </div>
            <button type="button" onClick={() => setSel(null)} className="text-[#8B98A5] hover:text-[#E6EDF3] text-sm">✕</button>
          </div>
          <div className="mt-2">
            <span className="text-xs px-2 py-0.5 rounded-full font-medium"
              style={{ background: `${SEV_COLOR[selected.sev]}22`, color: SEV_COLOR[selected.sev], border: `1px solid ${SEV_COLOR[selected.sev]}55` }}>
              {SEV_LABEL[selected.sev]}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 mt-4">
            <div className="panel p-3"><div className="text-xs text-[#8B98A5]">Anomaly score</div>
              <div className="mono text-xl" style={{ color: selected.eq.is_anomalous ? "#FF6A2B" : "#3FB68B" }}>{selected.eq.anomaly_score ?? "—"}</div></div>
            <div className="panel p-3"><div className="text-xs text-[#8B98A5]">RUL</div>
              <div className="mono text-xl text-[#FF6A2B]">{selected.eq.rul_days != null ? `${selected.eq.rul_days}d` : "—"}</div></div>
          </div>

          <div className="panel p-3 mt-2">
            <div className="text-xs text-[#8B98A5]">Maintenance status</div>
            <div className="text-sm mt-0.5" style={{ color: SEV_COLOR[selected.sev] }}>{maintStatus(selected.sev)}</div>
          </div>

          <div className="mt-4">
            <div className="text-sm font-medium mb-2">Open work orders <span className="text-[#8B98A5]">({selectedWOs.length})</span></div>
            {selectedWOs.length === 0 && <div className="text-xs text-[#8B98A5] panel p-3">No open work orders.</div>}
            <div className="space-y-1.5">
              {selectedWOs.slice(0, 8).map((w) => (
                <Link key={w.id} href={`/dashboard/work-orders/${w.id}`} className="panel p-2.5 text-xs block hover:border-[#4A90D9]">
                  <div className="flex items-center justify-between">
                    <span className="mono text-[#9fb0c0]">WO-{w.id.slice(0, 8)}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium text-[#E8B931]">
                      {w.status.replace("_", " ").toUpperCase()}
                    </span>
                  </div>
                  <div className="text-[#c3ced9] mt-1">{w.title}</div>
                </Link>
              ))}
            </div>
          </div>

          <div className="flex gap-2 mt-4">
            <Link href={`/equipment/${selected.eq.id}`}
              className="flex-1 text-center text-xs px-3 py-2 rounded bg-[#4A90D9] text-white font-medium">Open equipment view</Link>
            <a href={reportUrl(selected.eq.id)} target="_blank" rel="noreferrer"
              className="text-xs px-3 py-2 rounded bg-[#1C232C] border border-[#232B35] text-[#9fb0c0] hover:border-[#4A90D9]">Report (PDF)</a>
          </div>
        </div>
      )}
    </div>
  );
}
