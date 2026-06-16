// TS mirror of backend/schemas/cards.py + agent_models.py (schema parity).

export type Confidence = "High" | "Medium" | "Low";
export type RiskLevel = "low" | "medium" | "high" | "critical";

export interface Citation { kind: string; ref: string; chunk_id?: string | null; }
export interface Delegation { agent: string; text: string; ts?: string; }

export interface RootCause { rank: number; cause: string; confidence: Confidence; citation_refs: string[]; }

export interface Card {
  card_type: string;
  citation_refs?: string[];
  served_from_cache?: boolean;
  // diagnosis
  fault?: string; confidence?: Confidence; summary?: string;
  root_causes?: RootCause[]; recommended_next?: string;
  // checklist
  title?: string; steps?: { text: string; safety?: boolean; expected?: string | null }[];
  // risk / rul
  risk_level?: RiskLevel; justification?: string;
  rul_days?: number; rul_band?: number[]; contributing_sensors?: string[]; note?: string;
  // wait_assessment
  verdict?: "yes" | "yes_with_conditions" | "no"; days_to_window?: number;
  monitoring_plan?: string; procurement_callout?: string;
  // priority
  priority_score?: number; rank?: number;
  factors?: { name: string; raw: number; weight: number; contribution: number }[]; rationale?: string;
  // spares
  part_no?: string; stock_qty?: number; lead_time_days?: number; procurement_note?: string; proposal?: string;
  // sql (analytical)
  question?: string; sql?: string; columns?: string[]; rows?: (string | number | boolean | null)[][]; narration?: string;
  // honest-failure
  message?: string;
}

export interface ChatResponse {
  card: Card | null;
  delegations: Delegation[];
  citations: Citation[];
  intent?: string;
  query_class?: string;
  pending_action?: Record<string, unknown> | null;
  awaiting_approval?: boolean;
  session_id: string;
}

export interface Equipment {
  id: string; name: string; zone: string; criticality: number;
  anomaly_score?: number | null; is_anomalous?: boolean | null; rul_days?: number | null;
}

export interface EquipmentDetail extends Equipment {
  thresholds?: Record<string, { alarm?: number; trip?: number }>;
  health?: { anomaly_score: number; is_anomalous: boolean; rul_days: number;
             rul_band?: { band?: number[] }; contributing_sensors?: string[] } | null;
  sensors: { ts: string; vibration_de: number; bearing_temp: number }[];
}

export interface Alert { id: string; equipment_id: string; severity: RiskLevel | "info" | "warning"; title: string; created_at: string; }

export interface PlantSummary {
  availability_pct: number;
  open_alerts: number;
  at_risk_count: number;
  downtime_at_risk_inr: number;
  downtime_at_risk_label: string;
  assumptions: Record<string, string | number>;
}

export interface ScorecardModel {
  model: string;
  title: string;
  dataset?: string;
  algorithm?: string;
  serve_mode?: string;
  metrics: Record<string, string | number | null>;
  sample_label?: string | null;
  recorded?: Record<string, number | boolean>;
  live_inference?: Record<string, unknown> | null;
}
export interface Scorecard { models: ScorecardModel[]; count: number; }

export interface SearchItem {
  type: string; ref: string; title: string; excerpt: string;
  equipment_id?: string | null; ts?: string | null; score: number;
}

export interface WorkOrder {
  id: string; equipment_id: string; equipment_name?: string;
  title: string; description?: string | null; status: string;
  priority?: number | null; steps?: { text: string; done?: boolean; safety?: boolean }[];
  created_at: string; updated_at?: string; completed_at?: string | null;
  zone?: string; criticality?: number;
}

export interface Incident {
  id: string; equipment_id: string; equipment_name?: string;
  criticality?: number; occurred_at?: string | null; fault_code?: string;
  symptoms?: string; root_cause?: string; resolution?: string;
  downtime_hrs?: number; verified?: boolean;
  production_impact_inr?: number; production_impact_label?: string;
  failure_progression?: { stage: string; detail?: string }[];
}

export interface SpareCatalogItem {
  part_no: string; equipment_id: string; equipment_name?: string;
  description?: string; stock_qty: number; lead_time_days: number;
  supplier?: string; unit_cost_inr: number; rul_days?: number | null;
  procurement_action?: string; procurement_note?: string;
}

export interface OptimizerResult {
  items: (SpareCatalogItem & {
    shortage_risk: boolean; production_exposure_inr: number;
    production_exposure_label: string; recommended_action: string; rationale: string;
  })[];
  total_production_exposure_inr: number;
  total_production_exposure_label: string;
  at_risk_parts: number;
}

export interface ReliabilityData {
  equipment_id: string; name: string; zone?: string; criticality?: number;
  anomaly_score?: number; is_anomalous?: boolean; rul_days?: number;
  rul_band?: number[]; failure_probability?: number;
  contributing_sensors?: string[];
  sensor_series?: { ts: string; vibration_de: number; bearing_temp: number }[];
  trend_analysis?: { ts: string; vibration_avg: number }[];
  graph?: { nodes: { id: string; type: string; label: string }[];
             edges: { source: string; target: string; relation: string }[] };
}

export interface LeadershipROI {
  shutdown_cost_label: string; potential_failure_cost_label: string;
  expected_savings_label: string; assumptions: Record<string, string | number>;
  recommendations: {
    equipment_id: string; name: string; zone?: string;
    shutdown_cost_label: string; potential_failure_cost_label: string;
    expected_savings_label: string; roi: number; confidence: string;
    recommended_action: string; copilot_prompt: string;
  }[];
  top_recommendation?: LeadershipROI["recommendations"][0] | null;
}

export interface EquipmentContext {
  equipment_id: string; name: string; zone: string; criticality: number;
  anomaly_score?: number; is_anomalous?: boolean; rul_days?: number;
  contributing_sensors?: string[];
  open_alerts: { id: string; severity: string; title: string }[];
  open_work_orders: { id: string; title: string; status: string; priority?: number }[];
  spares: SpareCatalogItem[];
  downtime_at_risk_label: string;
}

export interface LogbookEntry {
  id: string; equipment_id: string; author_type: string;
  entry_type: string; content: Record<string, unknown>; created_at: string;
}
