import type { Alert, ChatResponse, Equipment, EquipmentDetail } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export const getEquipment = () => fetch(`${API}/equipment`, { cache: "no-store" }).then(j<Equipment[]>);
export const getEquipmentDetail = (id: string) =>
  fetch(`${API}/equipment/${id}`, { cache: "no-store" }).then(j<EquipmentDetail>);
export const getAlerts = () => fetch(`${API}/alerts`, { cache: "no-store" }).then(j<Alert[]>);

export const postChat = (body: {
  message: string; equipment_id?: string; session_id?: string; role?: string;
}) =>
  fetch(`${API}/chat`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }).then(j<ChatResponse>);

export const postApprove = (session_id: string, approved: boolean) =>
  fetch(`${API}/chat/approve`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id, approved }),
  }).then(j<ChatResponse>);
