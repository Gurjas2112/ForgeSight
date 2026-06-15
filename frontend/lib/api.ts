import type { Alert, ChatResponse, Equipment, EquipmentDetail, Scorecard } from "./types";
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
  email: string; password: string; full_name?: string; role: "engineer" | "admin";
}) =>
  fetch(`${API}/auth/signup`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }).then(j<{ ok: boolean; id: string; email: string; role: string }>);

export const reportUrl = (equipment_id: string) =>
  `${API}/reports/alert?equipment_id=${encodeURIComponent(equipment_id)}`;
