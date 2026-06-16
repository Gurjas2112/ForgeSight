import type {
  Alert, ChatResponse, Equipment, EquipmentContext, EquipmentDetail,
  Incident, LeadershipROI, LogbookEntry, OptimizerResult, PlantSummary,
  ReliabilityData, Scorecard, SearchItem, SpareCatalogItem, WorkOrder,
} from "./types";
import { getSupabase } from "./supabase";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

/** Authorization header with the current Supabase access token, when signed in. */
async function authHeaders(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  const sb = getSupabase();
  const token = sb ? (await sb.auth.getSession()).data.session?.access_token : null;
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

export const getEquipment = () => fetch(`${API}/equipment`, { cache: "no-store" }).then(j<Equipment[]>);
export const getEquipmentDetail = (id: string) =>
  fetch(`${API}/equipment/${id}`, { cache: "no-store" }).then(j<EquipmentDetail>);
export const getAlerts = () => fetch(`${API}/alerts`, { cache: "no-store" }).then(j<Alert[]>);
export const getPlantSummary = () => fetch(`${API}/plant/summary`, { cache: "no-store" }).then(j<PlantSummary>);
export const getScorecard = () => fetch(`${API}/models/scorecard`, { cache: "no-store" }).then(j<Scorecard>);

export const postChat = async (body: {
  message: string; equipment_id?: string; session_id?: string; role?: string;
}) =>
  fetch(`${API}/chat`, {
    method: "POST", headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  }).then(j<ChatResponse>);

export const postApprove = async (session_id: string, approved: boolean) =>
  fetch(`${API}/chat/approve`, {
    method: "POST", headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ session_id, approved }),
  }).then(j<ChatResponse>);

export const postFeedback = async (body: {
  verdict: "up" | "down" | "fixed"; equipment_id?: string; fault_code?: string;
  note?: string; session_id?: string;
}) =>
  fetch(`${API}/feedback`, {
    method: "POST", headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  }).then(j<{ ok: boolean; feedback_id: string; verified_record: string | null }>);

export const postSignup = (body: {
  email: string; password: string; full_name?: string; role?: "engineer";
}) =>
  fetch(`${API}/auth/signup`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }).then(j<{ ok: boolean; id: string; email: string; role: string }>);

export const reportUrl = (equipment_id: string) =>
  `${API}/reports/alert?equipment_id=${encodeURIComponent(equipment_id)}`;

export const searchEvidence = (params: { q?: string; types?: string; equipment_id?: string }) => {
  const q = new URLSearchParams();
  if (params.q) q.set("q", params.q);
  if (params.types) q.set("types", params.types);
  if (params.equipment_id) q.set("equipment_id", params.equipment_id);
  return fetch(`${API}/search?${q}`, { cache: "no-store" }).then(j<{ items: SearchItem[]; count: number }>);
};

export const getWorkOrders = (params?: { equipment_id?: string; status?: string }) => {
  const q = new URLSearchParams();
  if (params?.equipment_id) q.set("equipment_id", params.equipment_id);
  if (params?.status) q.set("status", params.status);
  return fetch(`${API}/work-orders?${q}`, { cache: "no-store" }).then(j<WorkOrder[]>);
};

export const getWorkOrder = (id: string) =>
  fetch(`${API}/work-orders/${id}`, { cache: "no-store" }).then(j<WorkOrder>);

export const patchWorkOrder = async (id: string, body: { status?: string; steps?: WorkOrder["steps"]; priority?: number }) =>
  fetch(`${API}/work-orders/${id}`, {
    method: "PATCH", headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  }).then(j<WorkOrder>);

export const workOrderExportUrl = (id: string, format: "json" | "pdf") =>
  `${API}/work-orders/${id}/export?format=${format}`;

export const getIncidents = (equipment_id?: string) => {
  const q = equipment_id ? `?equipment_id=${encodeURIComponent(equipment_id)}` : "";
  return fetch(`${API}/incidents${q}`, { cache: "no-store" }).then(j<Incident[]>);
};

export const getIncident = (id: string) =>
  fetch(`${API}/incidents/${id}`, { cache: "no-store" }).then(j<Incident>);

export const getIncidentReplay = (id: string) =>
  fetch(`${API}/incidents/${id}/replay`, { cache: "no-store" }).then(j<{ incident: Incident; sensors: { ts: string; vibration_de: number }[]; similar_failures: { ref: string; excerpt: string }[] }>);

export const getIncidentLessons = (id: string) =>
  fetch(`${API}/incidents/${id}/lessons`, { cache: "no-store" }).then(j<{ lessons: Incident[]; logbook: LogbookEntry[]; fault_code?: string }>);

export const getSpares = (params?: { equipment_id?: string; low_stock?: boolean }) => {
  const q = new URLSearchParams();
  if (params?.equipment_id) q.set("equipment_id", params.equipment_id);
  if (params?.low_stock) q.set("low_stock", "true");
  return fetch(`${API}/spares?${q}`, { cache: "no-store" }).then(j<SpareCatalogItem[]>);
};

export const getInventoryOptimizer = () =>
  fetch(`${API}/inventory/optimizer`, { cache: "no-store" }).then(j<OptimizerResult>);

export const getReliabilityPlant = () =>
  fetch(`${API}/reliability/plant`, { cache: "no-store" }).then(j<{ assets: ReliabilityData[]; count: number }>);

export const getReliability = (equipment_id: string) =>
  fetch(`${API}/reliability/${equipment_id}`, { cache: "no-store" }).then(j<ReliabilityData>);

export const getLeadershipROI = () =>
  fetch(`${API}/leadership/roi`, { cache: "no-store" }).then(j<LeadershipROI>);

export const getEquipmentContext = (id: string) =>
  fetch(`${API}/equipment/${id}/context`, { cache: "no-store" }).then(j<EquipmentContext>);

export const getLogbook = (equipment_id?: string) => {
  const q = equipment_id ? `?equipment_id=${encodeURIComponent(equipment_id)}` : "";
  return fetch(`${API}/maintenance/logbook${q}`, { cache: "no-store" }).then(j<LogbookEntry[]>);
};

export const postHandover = async (body: { equipment_id: string; notes: string; open_work_orders?: string[]; risk_context?: Record<string, unknown> }) =>
  fetch(`${API}/maintenance/handover`, {
    method: "POST", headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  }).then(j<{ ok: boolean; logbook_id: string }>);

export const evidenceUrl = (ref: string) => `${API}/evidence?ref=${encodeURIComponent(ref)}`;
